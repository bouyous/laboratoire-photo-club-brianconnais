# PhotoLabPro code reused for the club at the authorizing project owner’s request, 2026-10-13. MIT OR Apache-2.0.
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import json, os, platform, shutil, subprocess
from .paths import app_data_dir, cache_dir

SETTINGS_VERSION = 2

@dataclass
class PerformanceSettings:
    mode: str = 'auto'                 # auto / balanced / max / eco
    provider: str = 'auto'             # auto or explicit ORT EP name
    gpu_index: int = 0
    cpu_threads: int = 0               # 0 = automatic
    job_threads: int = 0               # 0 = automatic
    preview_megapixels: float = 1.6
    ai_tile: int = 0                   # 0 = automatic
    cache_gb: float = 8.0
    vram_percent: int = 80             # hard limit on CUDA; tile budget elsewhere
    keep_ai_sessions: bool = True
    max_ram_percent: int = 70          # protection against RAM exhaustion
    reserve_cpu_threads: int = 2       # leave Windows/browser responsive
    background_priority: bool = True   # OS should favor interactive apps
    legacy_vulkan: bool = True         # detect/use legacy Vulkan path when available
    thermal_guard: bool = True
    thermal_target_c: int = 80
    thermal_pause_c: int = 85
    thermal_resume_c: int = 74

    @classmethod
    def load(cls):
        p = settings_path()
        if not p.exists(): return cls()
        try:
            raw = json.loads(p.read_text(encoding='utf-8'))
            allowed = set(cls.__dataclass_fields__)
            return cls(**{k:v for k,v in raw.items() if k in allowed})
        except Exception:
            return cls()

    def save(self):
        p=settings_path(); p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(asdict(self),indent=2,ensure_ascii=False),encoding='utf-8')

    def normalized(self):
        self.gpu_index=max(0,int(self.gpu_index));self.cpu_threads=max(0,int(self.cpu_threads));self.job_threads=max(0,int(self.job_threads))
        self.preview_megapixels=float(min(8.0,max(0.5,self.preview_megapixels)))
        self.ai_tile=int(self.ai_tile) if int(self.ai_tile) in (0,128,192,256,384,512,768,1024) else 0
        self.cache_gb=float(min(256.0,max(0.5,self.cache_gb)));self.vram_percent=int(min(95,max(25,self.vram_percent)))
        self.max_ram_percent=int(min(94,max(35,int(self.max_ram_percent))));self.reserve_cpu_threads=max(0,int(self.reserve_cpu_threads))
        self.thermal_target_c=int(min(90,max(65,int(self.thermal_target_c))))
        self.thermal_pause_c=int(min(100,max(self.thermal_target_c+2,int(self.thermal_pause_c))))
        self.thermal_resume_c=int(min(self.thermal_target_c-2,max(50,int(self.thermal_resume_c))))
        if self.mode not in ('auto','balanced','max','eco'):self.mode='auto'
        return self


def settings_path() -> Path:
    return app_data_dir()/'performance.json'


def _run(args,timeout=4):
    try:
        p=subprocess.run(args,capture_output=True,text=False,timeout=timeout,check=False,creationflags=(0x08000000 if os.name=='nt' else 0))
        from .system_text import decode_system_output
        return decode_system_output(p.stdout).strip()
    except Exception:return ''


def _ram_gb():
    try:
        import psutil
        return psutil.virtual_memory().total/(1024**3)
    except Exception:
        if hasattr(os,'sysconf'):
            try:return os.sysconf('SC_PAGE_SIZE')*os.sysconf('SC_PHYS_PAGES')/(1024**3)
            except Exception:pass
        return 0.0


def _physical_cores():
    try:
        import psutil
        return int(psutil.cpu_count(logical=False) or 0)
    except Exception:return 0


def _nvidia_smi():
    exe=shutil.which('nvidia-smi')
    if not exe:return []
    out=_run([exe,'--query-gpu=name,memory.total','--format=csv,noheader,nounits'])
    result=[]
    for line in out.splitlines():
        try:
            name,mem=[x.strip() for x in line.rsplit(',',1)]; result.append({'name':name,'vram_gb':float(mem)/1024.0,'vendor':'NVIDIA'})
        except Exception:pass
    return result


def _windows_gpus():
    if os.name!='nt':return []
    ps=shutil.which('powershell') or shutil.which('pwsh')
    if not ps:return []
    script="Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json -Compress"
    out=_run([ps,'-NoProfile','-Command',script],timeout=6)
    try:
        data=json.loads(out);data=data if isinstance(data,list) else [data]
        res=[]
        for x in data:
            name=str(x.get('Name') or '').strip();ram=x.get('AdapterRAM') or 0
            if not name:continue
            vendor='NVIDIA' if 'nvidia' in name.lower() else 'AMD' if any(s in name.lower() for s in ('amd','radeon')) else 'Intel' if 'intel' in name.lower() else 'Autre'
            # AdapterRAM is often truncated to 4 GiB on modern cards, so treat it only as a fallback hint.
            res.append({'name':name,'vram_gb':float(ram)/(1024**3) if ram else 0.0,'vendor':vendor})
        return res
    except Exception:return []


def _mac_gpus():
    if platform.system()!='Darwin':return []
    out=_run(['system_profiler','SPDisplaysDataType','-json'],timeout=8)
    try:
        d=json.loads(out);res=[]
        for x in d.get('SPDisplaysDataType',[]):
            name=x.get('sppci_model') or x.get('_name') or 'GPU Apple';res.append({'name':str(name),'vram_gb':0.0,'vendor':'Apple'})
        return res
    except Exception:return []


def available_providers():
    try:
        import onnxruntime as ort
        return list(ort.get_available_providers())
    except Exception:return []


def detect_hardware():
    logical=int(os.cpu_count() or 1);physical=_physical_cores()
    gpus=_nvidia_smi()
    known={g['name'] for g in gpus}
    for g in (_windows_gpus()+_mac_gpus()):
        if g['name'] not in known:gpus.append(g);known.add(g['name'])
    return {
        'os':f'{platform.system()} {platform.release()}',
        'cpu':platform.processor() or platform.machine(),
        'logical_cores':logical,'physical_cores':physical,'ram_gb':_ram_gb(),
        'gpus':gpus,'providers':available_providers(),
    }


def best_vram_gb(info=None,gpu_index=0):
    info=info or detect_hardware();g=info.get('gpus') or []
    if not g:return 0.0
    idx=min(max(0,int(gpu_index)),len(g)-1)
    val=float(g[idx].get('vram_gb') or 0.0)
    # nvidia-smi entries are inserted first and are the reliable path for NVIDIA.
    return val


def auto_provider_order(info=None):
    info=info or detect_hardware();have=set(info.get('providers') or [])
    # CUDA is the preferred generic NVIDIA backend when present. Vendor EPs are next,
    # DirectML is the broad Windows DX12 fallback, then CPU.
    order=['CUDAExecutionProvider','NvTensorRtRtxExecutionProvider','TensorrtExecutionProvider',
           'MIGraphXExecutionProvider','OpenVINOExecutionProvider','QNNExecutionProvider',
           'DmlExecutionProvider','CoreMLExecutionProvider','CPUExecutionProvider']
    return [p for p in order if p in have]


def provider_chain(settings:PerformanceSettings,info=None):
    info=info or detect_hardware();have=set(info.get('providers') or [])
    # A native GPU/EP crash must not be retried on every launch. PhotoLab keeps
    # a small local quarantine list that can be reset from the Optimization dialog.
    try:
        from .provider_health import blocked_providers
        blocked=blocked_providers()
    except Exception:blocked=set()
    forced=os.environ.get('PLP_FORCE_PROVIDER','').strip()
    if forced and forced in have:
        return [forced]+[p for p in auto_provider_order(info) if p!=forced and p not in blocked]
    # A provider explicitly selected by the user is a deliberate override of
    # PhotoLab's automatic quarantine. The worker is still isolated, so a native
    # driver crash cannot take the GUI down and the job can fall back to CPU.
    if settings.provider!='auto' and settings.provider in have:
        return [settings.provider]+[p for p in auto_provider_order(info) if p!=settings.provider and p not in blocked]
    order=[p for p in auto_provider_order(info) if p not in blocked]
    if 'CPUExecutionProvider' in have and 'CPUExecutionProvider' not in order:order.append('CPUExecutionProvider')
    return order



def should_probe_directml(settings:PerformanceSettings, providers, chain, denoise_available:bool, attempted:bool=False) -> bool:
    """Return whether Auto mode must validate DirectML before benchmarking CPU.

    This is intentionally pure/testable because startup ordering is critical: a
    stale quarantine may make the current chain look CPU-only even though the
    DirectML runtime is installed. In that case PhotoLab must probe the GPU first.
    """
    if attempted or not denoise_available:return False
    selected=getattr(settings,'provider','auto')
    if selected not in ('auto','DmlExecutionProvider'):return False
    have=set(providers or [])
    if 'DmlExecutionProvider' not in have:return False
    # A previous successful stress profile must not suppress a new probe when
    # DirectML is currently quarantined or no longer first in the active chain.
    # This exact stale-state combination used to leave PhotoLab on CPU forever:
    # probe succeeds -> later real job crashes -> provider is blocked -> old
    # successful accelerator_profile remains -> startup incorrectly skips probe.
    active_first=(chain[0] if chain else 'CPUExecutionProvider')
    try:
        from .provider_health import blocked_providers
        dml_blocked='DmlExecutionProvider' in blocked_providers()
    except Exception:
        dml_blocked=False
    try:
        from .accelerator_profile import stress_verified
        if (not dml_blocked and active_first=='DmlExecutionProvider' and
            stress_verified('DmlExecutionProvider',getattr(settings,'gpu_index',0),3)):
            return False
    except Exception:
        pass
    # Probe even when DirectML is currently first: older profiles validated only
    # a single inference and were not sufficient to prove driver stability.
    return True

def _selected_gpu(info,gpu_index=0):
    g=list((info or {}).get('gpus') or [])
    if not g:return {}
    idx=min(max(0,int(gpu_index)),len(g)-1)
    return dict(g[idx] or {})


def is_integrated_gpu(info=None,gpu_index=0):
    """Best-effort iGPU/APU detection used only for conservative tile sizing."""
    info=info or detect_hardware();g=_selected_gpu(info,gpu_index)
    name=str(g.get('name') or '').lower();vendor=str(g.get('vendor') or '').lower();vram=float(g.get('vram_gb') or 0.0)
    hints=('radeon(tm) graphics','radeon graphics','vega','intel(r) uhd','intel uhd','iris','integrated','apu')
    if any(h in name for h in hints):return True
    # Windows often reports 512 MiB of dedicated memory for an APU while the
    # device actually uses several GiB of shared system memory. Treat this as an
    # iGPU hint, but only for AMD/Intel so old discrete cards are not penalized.
    return vendor in ('amd','intel') and 0 < vram <= 1.0


def auto_tile(settings:PerformanceSettings,kind='denoise',info=None):
    if settings.ai_tile:return int(settings.ai_tile)
    info=info or detect_hardware();vram=best_vram_gb(info,settings.gpu_index)*(settings.vram_percent/100.0)
    chain=provider_chain(settings,info);primary=chain[0] if chain else 'CPUExecutionProvider'
    igpu=is_integrated_gpu(info,settings.gpu_index)
    # DirectML on an APU must start conservatively. A 512px SCUNet tile can
    # exhaust the small dedicated heap even when Windows exposes lots of shared
    # GPU memory, which used to make PhotoLab fall back to CPU on Ryzen APUs.
    if primary=='DmlExecutionProvider' and igpu:
        if settings.mode=='eco':base=128
        elif settings.mode=='max':base=256
        else:base=192
    elif settings.mode=='eco':base=256
    elif settings.mode=='max':base=768 if vram>=10 else (384 if vram and vram<=2.5 else 512)
    elif vram and vram<=2.5:base=256
    elif vram and vram<=5:base=384
    elif vram>=10:base=768
    else:base=512
    if kind in ('superres','inpaint') and base>512:base=512
    if kind=='superres':
        if primary=='DmlExecutionProvider' and igpu:base=min(base,192)
        elif base>384 and vram and vram<8:base=384
    # A successful isolated provider probe may have established a lower safe
    # ceiling for this exact adapter. Respect it even in Performance mode.
    try:
        from .accelerator_profile import safe_tile
        cap=safe_tile(primary,settings.gpu_index)
        if cap>0:base=min(base,cap)
    except Exception:pass
    return max(64,int(base))


def _interactive_reserve_threads(info=None, performance=False):
    """Minimum logical CPU headroom that PhotoLab never consumes automatically.

    Heavy ONNX workloads can otherwise starve Qt and Windows even though they run in
    another process.  Performance mode is allowed to be aggressive, but it must
    still leave enough scheduler headroom for the desktop and the preview thread.
    """
    info=info or detect_hardware();logical=max(1,int(info.get('logical_cores') or 1))
    if logical<=2:return 0
    if performance:
        return 2 if logical>=8 else 1
    if logical>=16:return 4
    if logical>=10:return 3
    return 2 if logical>=6 else 1


def effective_cpu_threads(settings:PerformanceSettings,info=None):
    if settings.cpu_threads>0:return min(max(1,int(settings.cpu_threads)),max(1,int((info or detect_hardware()).get('logical_cores') or 1)))
    info=info or detect_hardware();logical=max(1,int(info.get('logical_cores') or 1));physical=int(info.get('physical_cores') or 0)
    if settings.mode=='eco':return max(1,(physical or logical)//2)
    requested=max(0,int(settings.reserve_cpu_threads))
    minimum=_interactive_reserve_threads(info,performance=(settings.mode=='max'))
    reserve=min(max(requested,minimum),max(0,logical-1))
    target=max(1,logical-reserve)
    # Balanced/eco work benefits little from filling SMT siblings and keeping the
    # physical-core cap greatly improves interactive latency. Performance mode can
    # use SMT, but never the last reserved logical threads.
    if settings.mode!='max' and physical:return max(1,min(physical,target))
    return target


def ort_cpu_threads(settings:PerformanceSettings, info=None, primary_provider:str|None=None):
    """CPU thread budget for one ONNX session.

    When a GPU EP is primary, CPU is a compatibility fallback, not a second full
    renderer. Limiting it prevents a partially-supported DirectML graph from
    silently saturating every core and freezing the UI.
    """
    info=info or detect_hardware();base=effective_cpu_threads(settings,info)
    primary=str(primary_provider or 'CPUExecutionProvider')
    if primary!='CPUExecutionProvider':
        logical=max(1,int(info.get('logical_cores') or 1))
        return max(1,min(base,4 if logical>=8 else 2))
    return base


def effective_job_threads(settings:PerformanceSettings,info=None):
    if settings.job_threads>0:return settings.job_threads
    info=info or detect_hardware();logical=max(1,int(info.get('logical_cores') or 1))
    if settings.mode=='eco':return max(2,min(4,logical//2))
    if settings.mode=='max':return min(16,logical)
    return min(8,max(2,logical//2))


def apply_cpu_runtime(settings:PerformanceSettings,thread_pool=None,info=None):
    info=info or detect_hardware();threads=effective_cpu_threads(settings,info);jobs=effective_job_threads(settings,info)
    try:
        import cv2
        cv2.setNumThreads(int(threads))
    except Exception:pass
    if thread_pool is not None:
        try:thread_pool.setMaxThreadCount(int(jobs))
        except Exception:pass
    apply_process_priority(settings)
    return {'cpu_threads':threads,'job_threads':jobs}


def cache_stats():
    root=cache_dir();total=0;count=0
    for p in root.rglob('*'):
        if p.is_file():
            try:total+=p.stat().st_size;count+=1
            except OSError:pass
    return {'bytes':total,'files':count}


def clear_cache():
    root=cache_dir()
    for p in sorted(root.rglob('*'),reverse=True):
        # Persisted inpainting masks are editing data required to replay history.
        if p.relative_to(root).parts[0]=='history':continue
        try:
            if p.is_file() or p.is_symlink():p.unlink()
            elif p!=root:p.rmdir()
        except OSError:pass
    root.mkdir(parents=True,exist_ok=True)



def memory_budget_gb(settings:PerformanceSettings, info=None):
    info=info or detect_hardware();ram=float(info.get('ram_gb') or 0.0)
    return ram*(settings.max_ram_percent/100.0) if ram>0 else 0.0


def estimated_ai_working_set_gb(kind:str, shape, tile:int=512):
    """Conservative working-set estimate, not a promise of exact RSS."""
    h,w=int(shape[0]),int(shape[1]);px=max(1,h*w)
    base=px*3*4/(1024**3)  # one RGB float32 image
    if kind=='superres':
        # original + 2x output (4x pixels) + blend weights + scratch/model workspace
        return base*(1 + 4 + 4/3 + 1.5)
    if kind=='denoise_fast':
        # NAFNet keeps a deeper activation pyramid than the simple pixel pipeline;
        # use a conservative allowance for one static 768px inference tile.
        return base*3.0 + (tile*tile*3*4*12)/(1024**3)
    if kind=='denoise':
        return base*3.8 + (tile*tile*3*4*6)/(1024**3)
    if kind=='denoise_extreme':
        # Three full-resolution denoise passes are streamed by tiles, but the
        # independent faithful/heavy outputs and fusion maps coexist briefly.
        return base*5.8 + (tile*tile*3*4*8)/(1024**3)
    if kind=='inpaint':
        return base*2.4 + (512*512*3*4*8)/(1024**3)
    return base*2.0


def apply_process_priority(settings:PerformanceSettings, heavy_worker:bool=False):
    """Keep the desktop and Qt event loop responsive during long processing."""
    if not settings.background_priority and not heavy_worker:return
    try:
        import psutil
        proc=psutil.Process()
        if os.name=='nt':
            # Heavy child workers always stay below the GUI process. Performance
            # means more throughput, not permission to starve Windows.
            proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if heavy_worker or settings.mode!='max' else psutil.NORMAL_PRIORITY_CLASS)
        else:
            try:proc.nice(7 if heavy_worker else 5)
            except Exception:pass
    except Exception:pass


def apply_heavy_worker_runtime(settings:PerformanceSettings, info=None, primary_provider:str|None=None):
    """Apply conservative CPU/runtime limits inside an isolated AI worker."""
    info=info or detect_hardware();threads=ort_cpu_threads(settings,info,primary_provider)
    for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','VECLIB_MAXIMUM_THREADS'):
        os.environ[name]=str(max(1,int(threads)))
    os.environ.setdefault('OMP_WAIT_POLICY','PASSIVE')
    os.environ.setdefault('KMP_BLOCKTIME','0')
    try:
        import cv2
        cv2.setNumThreads(max(1,int(threads)))
    except Exception:pass
    apply_process_priority(settings,heavy_worker=True)
    return {'cpu_threads':threads}


def legacy_acceleration_status():
    """Report old-hardware compute paths without claiming they can run every model."""
    out={'opencv_opencl':False,'opencv_opencl_device':'','ncnn_present':False,'vulkan_gpu_count':0}
    try:
        import cv2
        out['opencv_opencl']=bool(cv2.ocl.haveOpenCL())
        if out['opencv_opencl']:
            try:out['opencv_opencl_device']=str(cv2.ocl.Device.getDefault().name())
            except Exception:pass
    except Exception:pass
    try:
        import ncnn
        out['ncnn_present']=True
        if hasattr(ncnn,'get_gpu_count'):
            try:out['vulkan_gpu_count']=max(0,int(ncnn.get_gpu_count()))
            except Exception:pass
    except Exception:pass
    return out


def apply_front_profile(settings:PerformanceSettings, profile:str, info=None):
    """Apply the two simple resource profiles exposed on the main toolbar.

    Normal keeps headroom for Windows/mail/browser. Performance gives PhotoLab
    substantially more CPU/RAM/VRAM while keeping the preview scheduler itself
    non-blocking.
    """
    info=info or detect_hardware();logical=max(1,int(info.get('logical_cores') or 1))
    if str(profile).lower()=='performance':
        settings.mode='max';settings.vram_percent=92;settings.max_ram_percent=82 if float(info.get('ram_gb') or 0)>=24 else 78
        settings.reserve_cpu_threads=_interactive_reserve_threads(info,performance=True);settings.background_priority=True
    else:
        settings.mode='balanced';settings.vram_percent=72;settings.max_ram_percent=76 if float(info.get('ram_gb') or 0)>=24 else 68
        settings.reserve_cpu_threads=_interactive_reserve_threads(info,performance=False);settings.background_priority=True
    return settings.normalized()
