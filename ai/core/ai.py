# PhotoLabPro code reused for the club at the authorizing project owner’s request, 2026-10-13. MIT OR Apache-2.0.
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib, threading, time, os
import numpy as np
import cv2
from .paths import models_dir
from .color import linear_to_srgb,srgb_to_linear
from .performance import PerformanceSettings,detect_hardware,provider_chain as perf_provider_chain,auto_tile,best_vram_gb,effective_cpu_threads,ort_cpu_threads
from .noise import analyze_noise, local_noise_weight,recommended_strength
from .mask_refine import refine_mask_edges, semantic_prompt_points, merge_semantic_with_sam
from . import rust_core

@dataclass
class AIStatus:
    runtime:str='Absent'
    providers:tuple[str,...]=()
    denoise:bool=False
    denoise_fast:bool=False
    denoise_light:bool=False
    denoise_extreme:bool=False
    superres:bool=False
    inpaint:bool=False
    subject:bool=False
    semantic:bool=False
    sam2:bool=False
    portrait:bool=False

class CancelledError(RuntimeError):pass
class CancelToken:
    def __init__(self):self._event=threading.Event()
    def cancel(self):self._event.set()
    def check(self):
        if self._event.is_set():raise CancelledError('Traitement annulé')
    @property
    def cancelled(self):return self._event.is_set()

class AIManager:
    def __init__(self,model_dir:str|Path|None=None,performance:PerformanceSettings|None=None):
        self.model_dir=Path(model_dir) if model_dir else models_dir(); self.model_dir.mkdir(parents=True,exist_ok=True)
        self.performance=(performance or PerformanceSettings.load()).normalized(); self.hardware=detect_hardware()
        self.sessions={}; self._lock=threading.Lock(); self._run_locks={}
        self._sam2_fp=None; self._sam2_embedding=None; self._sam2_original_size=None

    def status(self):
        try:
            import onnxruntime as ort; providers=tuple(ort.get_available_providers()); runtime='ONNX Runtime'
        except Exception:providers=();runtime='Absent'
        return AIStatus(
            runtime=runtime,providers=providers,
            denoise=(self.model_dir/'scunet_color_real_psnr.onnx').exists() and (self.model_dir/'scunet_color_real_psnr.onnx.data').exists(),
            denoise_fast=(self.model_dir/'nafnet_sidd_w32.onnx').exists(),
            denoise_light=(self.model_dir/'scunet_color_15.onnx').exists() and (self.model_dir/'scunet_color_15.onnx.data').exists(),
            denoise_extreme=(self.model_dir/'scunet_color_50.onnx').exists() and (self.model_dir/'scunet_color_50.onnx.data').exists(),
            superres=(self.model_dir/'real_esrgan_x2.onnx').exists(),
            inpaint=(self.model_dir/'inpainting_lama_2025jan.onnx').exists(),
            subject=(self.model_dir/'birefnet-lite-1024.onnx').exists(),
            semantic=(self.model_dir/'segformer_ade20k_b0.onnx').exists(),
            sam2=(self.model_dir/'sam2_hiera_tiny.encoder.onnx').exists() and (self.model_dir/'sam2_hiera_tiny.decoder.onnx').exists(),
            portrait=(self.model_dir/'face_parsing_bisenet_resnet18.onnx').exists())

    def clear_sessions(self):
        with self._lock:
            self.sessions.clear()
            self._run_locks.clear()
            self._sam2_fp=None; self._sam2_embedding=None; self._sam2_original_size=None

    def clear_sam2_embedding(self):
        self._sam2_fp=None; self._sam2_embedding=None; self._sam2_original_size=None

    def set_performance(self,settings:PerformanceSettings):
        self.performance=settings.normalized(); self.hardware=detect_hardware(); self.clear_sessions()

    def provider_chain(self):
        return perf_provider_chain(self.performance,self.hardware)

    def provider_label(self):
        p=self.provider_chain(); labels={'DmlExecutionProvider':'DirectML / DirectX 12','CUDAExecutionProvider':'NVIDIA CUDA','NvTensorRtRtxExecutionProvider':'NVIDIA TensorRT RTX','TensorrtExecutionProvider':'NVIDIA TensorRT','MIGraphXExecutionProvider':'AMD MIGraphX','QNNExecutionProvider':'Qualcomm QNN','CoreMLExecutionProvider':'CoreML / Apple Silicon','OpenVINOExecutionProvider':'Intel OpenVINO','CPUExecutionProvider':'CPU'}
        return labels.get(p[0],p[0] if p else 'Aucun moteur ONNX') if p else 'Aucun moteur ONNX'


    def operation_geometry(self,kind,shape):
        h,w=int(shape[0]),int(shape[1])
        if kind=='denoise_fast':
            tile=768;overlap=96;scale=1
        else:
            tile=auto_tile(self.performance,kind,self.hardware)
            if kind in ('denoise','denoise_extreme'):overlap=max(24,tile//10);scale=1
            elif kind=='superres':overlap=max(16,tile//12);scale=2
            elif kind=='inpaint':tile=512;overlap=96;scale=1
            else:overlap=max(16,tile//12);scale=1
        steps=len(self._positions(h,tile,overlap))*len(self._positions(w,tile,overlap))
        return {'tile':int(tile),'overlap':int(overlap),'scale':int(scale),'steps':int(steps)}

    def model_fingerprint(self,key):
        mapping={'denoise':['nafnet_sidd_w32.onnx','scunet_color_real_psnr.onnx','scunet_color_real_psnr.onnx.data','scunet_color_15.onnx','scunet_color_15.onnx.data','scunet_color_50.onnx','scunet_color_50.onnx.data'],'superres':['real_esrgan_x2.onnx'],'inpaint':['inpainting_lama_2025jan.onnx'],'subject':['birefnet-lite-1024.onnx'],'semantic':['segformer_ade20k_b0.onnx'],'sam2':['sam2_hiera_tiny.encoder.onnx','sam2_hiera_tiny.decoder.onnx'],'portrait':['face_parsing_bisenet_resnet18.onnx']}
        h=hashlib.sha256()
        if key in ('inpaint','denoise','portrait'):h.update(b'photolab-4.15-processing-v1')
        for name in mapping.get(key,[]):
            p=self.model_dir/name
            try:
                st=p.stat();h.update(f'{name}|{st.st_size}|{st.st_mtime_ns}'.encode())
            except OSError:h.update(f'{name}|missing'.encode())
        return h.hexdigest()

    def _session(self,key,path):
        import onnxruntime as ort
        with self._lock:
            if key in self.sessions:return self.sessions[key]
            opts=ort.SessionOptions();opts.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            providers=self.provider_chain() or ['CPUExecutionProvider']
            primary_provider=providers[0] if providers else 'CPUExecutionProvider'
            cpu_threads=ort_cpu_threads(self.performance,self.hardware,primary_provider)
            opts.intra_op_num_threads=max(1,int(cpu_threads));opts.inter_op_num_threads=1
            # A forced provider is used by the isolated accelerator probe. Make
            # that probe strict: if the model cannot be assigned completely to
            # the requested EP, session creation must fail instead of silently
            # executing unsupported nodes on CPU. Normal editing keeps CPU
            # fallback enabled for broad compatibility.
            forced_provider=os.environ.get('PLP_FORCE_PROVIDER','').strip()
            strict_forced=bool(forced_provider and forced_provider!='CPUExecutionProvider' and forced_provider in providers and os.environ.get('PLP_ALLOW_CPU_FALLBACK','0')!='1')
            if strict_forced:
                providers=[forced_provider]
                try:opts.add_session_config_entry('session.disable_cpu_ep_fallback','1')
                except Exception:pass
            configured=[]
            vram=best_vram_gb(self.hardware,self.performance.gpu_index)
            for provider in providers:
                if provider=='CUDAExecutionProvider':
                    options={'device_id':str(self.performance.gpu_index),'arena_extend_strategy':'kSameAsRequested','cudnn_conv_algo_search':'DEFAULT'}
                    if vram>0:options['gpu_mem_limit']=str(int(vram*(1024**3)*(self.performance.vram_percent/100.0)))
                    configured.append((provider,options))
                elif provider=='DmlExecutionProvider':
                    configured.append((provider,{'device_id':str(self.performance.gpu_index)}))
                elif provider=='OpenVINOExecutionProvider':
                    configured.append((provider,{'device_type':'AUTO'}))
                else:configured.append(provider)
            # DirectML explicitly requires sequential execution and memory-pattern disabled.
            if 'DmlExecutionProvider' in providers:
                opts.enable_mem_pattern=False;opts.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
            sess=ort.InferenceSession(str(path),sess_options=opts,providers=configured)
            self.sessions[key]=sess;self._run_locks[key]=threading.Lock();return sess

    def _run(self,key,sess,outputs,feeds):
        # DirectML does not allow concurrent Run calls on one session; serializing is also safe on other EPs.
        lock=self._run_locks.setdefault(key,threading.Lock())
        with lock:return sess.run(outputs,feeds)

    @staticmethod
    def _positions(size,tile,overlap):
        native=rust_core.tile_positions(size,tile,overlap)
        if native is not None:return native
        if size<=tile:return [0]
        stride=max(8,tile-overlap);out=list(range(0,size-tile+1,stride))
        if out[-1]!=size-tile:out.append(size-tile)
        return out

    @staticmethod
    def _blend_window(h,w):
        wy=np.maximum(np.hanning(max(2,h)),0.05).astype(np.float32);wx=np.maximum(np.hanning(max(2,w)),0.05).astype(np.float32)
        return np.outer(wy,wx)[...,None]

    def _tiled_rgb(self,key,sess,img,tile,overlap,scale,input_name,output_name,progress=None,cancel=None,align=1,tile_selector=None):
        x=np.ascontiguousarray(np.clip(img,0,1).astype(np.float32));h,w=x.shape[:2];tile=max(align,(tile//align)*align)
        ys=self._positions(h,tile,overlap);xs=self._positions(w,tile,overlap)
        out=np.zeros((h*scale,w*scale,3),np.float32);weights=np.zeros((h*scale,w*scale,1),np.float32);total=len(xs)*len(ys);done=0
        for y in ys:
            for xx in xs:
                if cancel:cancel.check()
                patch=x[y:min(y+tile,h),xx:min(xx+tile,w)];ph,pw=patch.shape[:2]
                # Confort may skip genuinely clean tiles. They are copied through
                # unchanged, which saves inference time without softening detail.
                skip=bool(tile_selector is not None and not tile_selector(patch,y,xx))
                if skip:
                    pred=patch.copy()
                else:
                    pad_h=(align-ph%align)%align;pad_w=(align-pw%align)%align
                    target_h=max(ph+pad_h,min(tile,h if h>=align else align));target_w=max(pw+pad_w,min(tile,w if w>=align else align))
                    extra_h=max(0,target_h-ph);extra_w=max(0,target_w-pw)
                    p2=patch
                    if extra_h or extra_w:p2=cv2.copyMakeBorder(p2,0,extra_h,0,extra_w,cv2.BORDER_REFLECT_101)
                    tensor=p2.transpose(2,0,1)[None].astype(np.float32)
                    pred=self._run(key,sess,[output_name],{input_name:tensor})[0][0].transpose(1,2,0)
                    pred=np.clip(pred,0,1)[:ph*scale,:pw*scale]
                win=self._blend_window(ph*scale,pw*scale);oy,ox=y*scale,xx*scale
                out[oy:oy+ph*scale,ox:ox+pw*scale]+=pred*win;weights[oy:oy+ph*scale,ox:ox+pw*scale]+=win;done+=1
                if progress:progress(done,total)
        return np.clip(out/np.maximum(weights,1e-6),0,1)

    def _tiled_rgb_static(self,key,sess,img,tile,overlap,input_name,output_name,progress=None,cancel=None,tile_selector=None):
        """Tile an RGB image for a model with a fixed square input shape.

        NAFNet from the darktable model repository is exported as 768x768. Edge
        patches and small photos are mirror-padded to that exact shape, while
        only the original patch area is blended back into the result.
        """
        x=np.ascontiguousarray(np.clip(img,0,1).astype(np.float32));h,w=x.shape[:2]
        tile=max(32,int(tile));overlap=max(0,min(tile-8,int(overlap)))
        ys=self._positions(h,tile,overlap);xs=self._positions(w,tile,overlap)
        out=np.zeros((h,w,3),np.float32);weights=np.zeros((h,w,1),np.float32);total=len(xs)*len(ys);done=0
        for y in ys:
            for xx in xs:
                if cancel:cancel.check()
                patch=x[y:min(y+tile,h),xx:min(xx+tile,w)];ph,pw=patch.shape[:2]
                skip=bool(tile_selector is not None and not tile_selector(patch,y,xx))
                if skip:
                    pred=patch.copy()
                else:
                    p2=patch
                    pad_h=max(0,tile-ph);pad_w=max(0,tile-pw)
                    if pad_h or pad_w:
                        # REFLECT_101 needs at least two pixels on the padded axis.
                        border=cv2.BORDER_REFLECT_101 if ph>1 and pw>1 else cv2.BORDER_REPLICATE
                        p2=cv2.copyMakeBorder(p2,0,pad_h,0,pad_w,border)
                    tensor=np.ascontiguousarray(p2.transpose(2,0,1)[None],dtype=np.float32)
                    pred=self._run(key,sess,[output_name],{input_name:tensor})[0][0].transpose(1,2,0)
                    pred=np.clip(pred,0,1)[:ph,:pw]
                win=self._blend_window(ph,pw);out[y:y+ph,xx:xx+pw]+=pred*win;weights[y:y+ph,xx:xx+pw]+=win
                done+=1
                if progress:progress(done,total)
        return np.clip(out/np.maximum(weights,1e-6),0,1)

    def _denoise_nafnet(self,img_encoded,progress=None,cancel=None,tile_selector=None):
        path=self.model_dir/'nafnet_sidd_w32.onnx';sess=self._session('denoise_fast',path)
        inp=sess.get_inputs()[0];out=sess.get_outputs()[0].name
        shape=list(inp.shape or [])
        try:tile=int(shape[-1]) if isinstance(shape[-1],int) else 768
        except Exception:tile=768
        # The published darktable model has a fixed 768px input. 96px overlap is
        # enough to hide seams while keeping the number of expensive runs low.
        overlap=max(48,min(96,tile//8))
        return self._tiled_rgb_static('denoise_fast',sess,img_encoded,tile,overlap,inp.name,out,progress,cancel,tile_selector)

    def benchmark_inference_tile(self, kind, tile):
        """Time one real ONNX inference on a synthetic tile.

        Used by the first-run machine calibration so no user photo has to act as
        a benchmark. Session creation/warmup is handled naturally by _session.
        """
        tile=max(32,int(tile))
        if kind=='denoise_fast':
            if not self.status().denoise_fast:raise FileNotFoundError('Modèle NAFNet absent')
            sess=self._session('denoise_fast_bench',self.model_dir/'nafnet_sidd_w32.onnx')
            shape=list(sess.get_inputs()[0].shape or [])
            try:tile=int(shape[-1]) if isinstance(shape[-1],int) else 768
            except Exception:tile=768
        elif kind=='denoise':
            if not self.status().denoise:raise FileNotFoundError('Modèle SCUNet absent')
            tile=max(8,(tile//8)*8)
            sess=self._session('denoise',self.model_dir/'scunet_color_real_psnr.onnx')
        elif kind=='superres':
            if not self.status().superres:raise FileNotFoundError('Modèle Real-ESRGAN x2 absent')
            sess=self._session('superres',self.model_dir/'real_esrgan_x2.onnx')
        else:
            raise ValueError('Benchmark IA non supporté: '+str(kind))
        inp=sess.get_inputs()[0].name;out=sess.get_outputs()[0].name
        # Fixed deterministic content avoids benchmark noise from random allocation.
        x=np.linspace(0.05,0.95,tile*tile*3,dtype=np.float32).reshape(tile,tile,3)
        tensor=np.ascontiguousarray(x.transpose(2,0,1)[None])
        t0=time.perf_counter();self._run(kind,sess,[out],{inp:tensor});return max(1e-6,time.perf_counter()-t0)

    def probe_inference(self, kind='denoise', tile=64, repeats=1):
        """Stress-test one provider with repeated real SCUNet inference.

        A single DirectML inference can succeed while the driver crashes after a
        few Run calls. The isolated startup probe therefore repeats the same
        workload several times before an accelerator is considered stable.
        """
        tile=max(32,int(tile));repeats=max(1,int(repeats))
        if kind=='denoise_fast':
            if not self.status().denoise_fast:raise FileNotFoundError('Modèle NAFNet absent')
            sess=self._session('denoise_fast_probe',self.model_dir/'nafnet_sidd_w32.onnx')
            shape=list(sess.get_inputs()[0].shape or [])
            try:tile=int(shape[-1]) if isinstance(shape[-1],int) else 768
            except Exception:tile=768
            run_key='denoise_fast_probe'
        elif kind=='denoise':
            if not self.status().denoise:raise FileNotFoundError('Modèle SCUNet absent')
            tile=max(8,(tile//8)*8)
            sess=self._session('denoise_probe',self.model_dir/'scunet_color_real_psnr.onnx')
            run_key='denoise_probe'
        else:
            raise ValueError('Probe non supporté: '+str(kind))
        inp=sess.get_inputs()[0].name;out=sess.get_outputs()[0].name
        x=np.linspace(0.05,0.95,tile*tile*3,dtype=np.float32).reshape(tile,tile,3)
        tensor=np.ascontiguousarray(x.transpose(2,0,1)[None])
        vals=[]
        for _ in range(repeats):
            t0=time.perf_counter();self._run(run_key,sess,[out],{inp:tensor});vals.append(max(1e-6,time.perf_counter()-t0))
        providers=list(sess.get_providers())
        core=float(np.median(vals[1:] or vals))
        return {'ok':True,'seconds':core,'runs':repeats,'providers':providers,'primary':providers[0] if providers else 'CPUExecutionProvider','gpu_index':int(self.performance.gpu_index),'kind':kind,'tile':int(tile)}

    @staticmethod
    def _stage_progress(progress, start, span):
        if progress is None:return None
        def cb(done,total):
            frac=float(done)/max(1,float(total));progress(int(start+span*frac),1000)
        return cb

    def _denoise_model(self,key,filename,img_encoded,progress=None,cancel=None,tile_selector=None,comfort=False):
        sess=self._session(key,self.model_dir/filename);inp=sess.get_inputs()[0].name;out=sess.get_outputs()[0].name
        tile=auto_tile(self.performance,'denoise',self.hardware)
        # Confort prioritises throughput: less overlap is sufficient for the weak
        # sigma15 model and the Hann blend still removes visible tile seams.
        overlap=max(16,tile//16) if comfort else max(24,tile//10)
        return self._tiled_rgb(key,sess,img_encoded,tile,overlap,1,inp,out,progress,cancel,8,tile_selector=tile_selector)

    def denoise(self,img,strength=1.0,mode='auto',iso=None,progress=None,cancel=None):
        """Adaptive professional denoising.

        comfort: NAFNet SIDD width32 first; old SCUNet sigma15 only as fallback.
        quality: faithful blind real-world SCUNet PSNR.
        extreme: independent faithful + sigma50 passes, adaptive local fusion,
                 followed by a conservative cleanup pass in noisy/flat zones.
        auto: choose from measured image noise + ISO metadata.
        """
        st=self.status()
        has_fast=bool(getattr(st,'denoise_fast',False));has_light=bool(getattr(st,'denoise_light',False));has_quality=bool(getattr(st,'denoise',False));has_extreme=bool(getattr(st,'denoise_extreme',False))
        if not (has_quality or has_fast or has_light):raise FileNotFoundError('Aucun modèle de débruitage installé')
        analysis=analyze_noise(img,iso)
        requested=str(mode or 'auto').strip().lower()
        aliases={'auto':'auto','confort':'comfort','comfort':'comfort','qualité':'quality','qualite':'quality','quality':'quality','extrême':'extreme','extreme':'extreme'}
        requested=aliases.get(requested,requested)
        chosen=analysis.recommended_mode if requested=='auto' else requested
        base=np.asarray(img,dtype=np.float32);base_sdr=np.clip(base,0,1);hdr_residual=np.maximum(base-1.0,0.0)
        encoded=linear_to_srgb(base_sdr).astype(np.float32)
        s=float(np.clip(strength,0,1))
        if requested=='auto':s=min(s,recommended_strength(analysis))

        if chosen=='comfort':
            # Daily/default path: NAFNet width32 is a substantially lighter CNN
            # than SCUNet. It is the first choice for speed; the legacy sigma15
            # model is retained only as a compatibility fallback.
            def comfort_tile_selector(patch,_y,_x):
                if patch.size<64:return True
                y=(0.2126*patch[...,0]+0.7152*patch[...,1]+0.0722*patch[...,2]).astype(np.float32)
                blur=cv2.GaussianBlur(y,(0,0),1.0);res=float(np.median(np.abs(y-blur)))
                dark=float(np.mean(y<0.18))
                return (res>0.0028) or (dark>0.22) or analysis.score>=24
            if has_fast:
                clean_e=self._denoise_nafnet(encoded,progress,cancel,tile_selector=comfort_tile_selector)
            elif has_light:
                try:
                    clean_e=self._denoise_model('denoise_light','scunet_color_15.onnx',encoded,progress,cancel,tile_selector=comfort_tile_selector,comfort=True)
                except TypeError as e:
                    if 'unexpected keyword argument' not in str(e):raise
                    clean_e=self._denoise_model('denoise_light','scunet_color_15.onnx',encoded,progress,cancel)
            else:
                clean_e=self._denoise_model('denoise','scunet_color_real_psnr.onnx',encoded,progress,cancel,tile_selector=comfort_tile_selector,comfort=True)
            clean=srgb_to_linear(clean_e)
            return np.maximum(0.0,base_sdr*(1-s)+clean*s+hdr_residual).astype(np.float32)

        if chosen=='quality' or not has_extreme:
            if has_quality:
                clean_e=self._denoise_model('denoise','scunet_color_real_psnr.onnx',encoded,progress,cancel)
            elif has_fast:
                clean_e=self._denoise_nafnet(encoded,progress,cancel)
            else:
                raise FileNotFoundError('Modèle Qualité absent')
            clean=srgb_to_linear(clean_e)
            return np.maximum(0.0,base_sdr*(1-s)+clean*s+hdr_residual).astype(np.float32)

        # EXTREME: two independent specialists avoid serial over-smoothing.
        def stage_cb(stage):
            if progress is None:return None
            def cb(done,total):progress(stage*max(1,int(total))+int(done),3*max(1,int(total)))
            return cb
        if not has_quality:
            clean_e=self._denoise_nafnet(encoded,progress,cancel)
            clean=srgb_to_linear(clean_e)
            return np.maximum(0.0,base_sdr*(1-s)+clean*s+hdr_residual).astype(np.float32)
        faithful=self._denoise_model('denoise','scunet_color_real_psnr.onnx',encoded,stage_cb(0),cancel)
        heavy=self._denoise_model('denoise_extreme','scunet_color_50.onnx',encoded,stage_cb(1),cancel)
        if cancel:cancel.check()
        w=local_noise_weight(img)[...,None]
        # Severe global noise moves the blend toward sigma50, while strong image
        # detail locally keeps the faithful real-world result.
        global_bias=float(np.clip((analysis.score-58.0)/42.0,0,1))*0.18
        w=np.clip(w+global_bias,0.10,0.94).astype(np.float32)
        fused=faithful*(1-w)+heavy*w

        # A final real-world cleanup is intentionally weak and only accepted in
        # low-detail/noisy areas. It makes Extreme slower but more useful on very
        # high ISO files without turning edges into wax.
        final_pass=self._denoise_model('denoise','scunet_color_real_psnr.onnx',fused,stage_cb(2),cancel)
        post=np.clip((w-0.28)/0.72,0,1)*0.34
        fused=fused*(1-post)+final_pass*post
        clean=srgb_to_linear(np.clip(fused,0,1))
        return np.maximum(0.0,base_sdr*(1-s)+clean*s+hdr_residual).astype(np.float32)

    def superres2x(self,img,progress=None,cancel=None):
        if not self.status().superres:raise FileNotFoundError('Modèle Real-ESRGAN x2 absent')
        sess=self._session('superres',self.model_dir/'real_esrgan_x2.onnx');inp=sess.get_inputs()[0].name;out=sess.get_outputs()[0].name
        encoded=linear_to_srgb(np.clip(img,0,1))
        tile=auto_tile(self.performance,'superres',self.hardware);up=self._tiled_rgb('superres',sess,encoded,tile,max(16,tile//12),2,inp,out,progress,cancel,1)
        return np.clip(srgb_to_linear(up),0,1)

    def subject_mask(self,img,quality='precise',progress=None,cancel=None):
        if not self.status().subject:raise FileNotFoundError('Modèle BiRefNet Lite absent')
        if cancel:cancel.check()
        sess=self._session('subject',self.model_dir/'birefnet-lite-1024.onnx')
        x=linear_to_srgb(np.clip(img.astype(np.float32),0,1));h,w=x.shape[:2]
        resized=cv2.resize(x,(1024,1024),interpolation=cv2.INTER_AREA if max(h,w)>1024 else cv2.INTER_CUBIC)
        mean=np.array([0.485,0.456,0.406],np.float32);std=np.array([0.229,0.224,0.225],np.float32)
        tensor=((resized-mean)/std).transpose(2,0,1)[None].astype(np.float32)
        inp=sess.get_inputs()[0].name;out=sess.get_outputs()[-1].name
        logits=self._run('subject',sess,[out],{inp:tensor})[0]
        logits=np.squeeze(logits).astype(np.float32);logits=np.clip(logits,-50,50);mask=1.0/(1.0+np.exp(-logits))
        mask=cv2.resize(mask,(w,h),interpolation=cv2.INTER_LINEAR);mask=cv2.GaussianBlur(mask,(0,0),0.8)
        q=str(quality or 'precise').lower()
        if q in ('precise','very_precise','tres_precis','très précis'):
            mask=refine_mask_edges(img,mask,'very_precise' if q.startswith('very') or 'tres' in q or 'très' in q else 'precise','subject')
        if q in ('very_precise','tres_precis','très précis') and self.status().sam2:
            pts=semantic_prompt_points(mask,6,8)
            if pts:
                try:mask=merge_semantic_with_sam(mask,self.sam2_mask(img,pts,cancel=cancel))
                except Exception:pass
            mask=refine_mask_edges(img,mask,'very_precise','subject')
        if progress:progress(1,1)
        return np.clip(mask,0,1)

    def semantic_mask(self,img,class_ids,quality='precise',kind='generic',progress=None,cancel=None):
        if not self.status().semantic:raise FileNotFoundError('Modèle SegFormer ADE20K absent')
        if cancel:cancel.check()
        sess=self._session('semantic',self.model_dir/'segformer_ade20k_b0.onnx')
        x=linear_to_srgb(np.clip(img.astype(np.float32),0,1));h,w=x.shape[:2]
        resized=cv2.resize(x,(512,512),interpolation=cv2.INTER_AREA if max(h,w)>512 else cv2.INTER_CUBIC)
        mean=np.array([0.485,0.456,0.406],np.float32);std=np.array([0.229,0.224,0.225],np.float32)
        tensor=((resized-mean)/std).transpose(2,0,1)[None].astype(np.float32)
        inp=sess.get_inputs()[0].name;out=sess.get_outputs()[0].name
        logits=self._run('semantic',sess,[out],{inp:tensor})[0][0].astype(np.float32)
        # Output is [150,H/4,W/4]. Sum softmax probabilities for requested ADE20K labels.
        logits-=np.max(logits,axis=0,keepdims=True);ex=np.exp(np.clip(logits,-50,0));probs=ex/np.maximum(np.sum(ex,axis=0,keepdims=True),1e-8)
        ids=[int(i) for i in class_ids if 0<=int(i)<probs.shape[0]]
        if not ids:return np.zeros((h,w),np.float32)
        mask=np.sum(probs[ids],axis=0);mask=cv2.resize(mask,(w,h),interpolation=cv2.INTER_LINEAR)
        # Semantic probabilities are conservative; remap around useful confidence levels and feather.
        mask=np.clip((mask-0.10)/0.65,0,1);mask=cv2.GaussianBlur(mask,(0,0),0.9)
        q=str(quality or 'precise').lower();rq='very_precise' if q in ('very_precise','tres_precis','très précis') else q
        if rq in ('precise','very_precise'):
            mask=refine_mask_edges(img,mask,rq,kind)
        if rq=='very_precise' and self.status().sam2 and str(kind).lower() not in ('people','personnes'):
            pts=semantic_prompt_points(mask,8,10)
            if pts:
                try:mask=merge_semantic_with_sam(mask,self.sam2_mask(img,pts,cancel=cancel))
                except Exception:pass
            mask=refine_mask_edges(img,mask,'very_precise',kind)
        if progress:progress(1,1)
        return np.clip(mask,0,1)



    def face_parse_regions(self,img,quality='precise',progress=None,cancel=None):
        if cancel:cancel.check()
        image=np.asarray(img,np.float32);h,w=image.shape[:2]
        encoded=(linear_to_srgb(np.clip(image,0,1))*255).astype(np.uint8)
        scale=min(1.,1000/max(h,w));small=cv2.resize(cv2.cvtColor(encoded,cv2.COLOR_RGB2BGR),(max(1,round(w*scale)),max(1,round(h*scale))))
        detector=cv2.FaceDetectorYN.create(str(Path(__file__).resolve().parents[1]/'resources/face/yunet.onnx'),'',(small.shape[1],small.shape[0]),.75,.3,5000)
        _,detections=detector.detect(small)
        faces=[] if detections is None else detections[:,:4]
        if len(faces)==0:raise ValueError('Aucun visage suffisamment visible. Utilisez Sujet ou le pinceau pour cette photo.')
        result={}
        for index,(x,y,fw,fh) in enumerate(faces):
            if cancel:cancel.check()
            x,y,fw,fh=(float(v)/scale for v in (x,y,fw,fh))
            side=max(fw,fh)*1.6;cx=x+fw/2;cy=y+fh/2
            x0=max(0,int(cx-side/2));y0=max(0,int(cy-side/2));x1=min(w,int(cx+side/2));y1=min(h,int(cy+side/2))
            regions=self._parse_face_crop(image[y0:y1,x0:x1],quality=quality,cancel=cancel)
            for name,region in regions.items():
                mask=np.zeros((h,w),np.float32);mask[y0:y1,x0:x1]=region
                result[name+((' '+str(index+1)) if len(faces)>1 else '')]=mask
            if progress:progress(index+1,len(faces))
        return result

    def _parse_face_crop(self,img,quality='precise',progress=None,cancel=None):
        """Return independent portrait masks for skin, eyes and lips."""
        if not self.status().portrait:raise FileNotFoundError('Modèle BiSeNet portrait absent')
        if cancel:cancel.check()
        sess=self._session('portrait',self.model_dir/'face_parsing_bisenet_resnet18.onnx')
        x=linear_to_srgb(np.clip(img.astype(np.float32),0,1));h,w=x.shape[:2]
        resized=cv2.resize(x,(512,512),interpolation=cv2.INTER_AREA if max(h,w)>512 else cv2.INTER_CUBIC)
        mean=np.array([0.485,0.456,0.406],np.float32);std=np.array([0.229,0.224,0.225],np.float32)
        tensor=((resized-mean)/std).transpose(2,0,1)[None].astype(np.float32)
        inp=sess.get_inputs()[0].name;outs=self._run('portrait',sess,None,{inp:tensor})
        if not outs:raise RuntimeError('Sortie BiSeNet portrait absente')
        logits=np.asarray(outs[0],np.float32)
        if logits.ndim==4:logits=logits[0]
        if logits.ndim!=3 or logits.shape[0]<14:raise RuntimeError('Format du modèle de portrait inattendu')
        logits-=np.max(logits,axis=0,keepdims=True);ex=np.exp(np.clip(logits,-40,0));probs=ex/np.maximum(np.sum(ex,axis=0,keepdims=True),1e-8)
        def region(ids,lo=0.16,hi=0.58,blur=0.75):
            m=np.sum(probs[ids],axis=0);m=np.clip((m-lo)/max(1e-5,hi-lo),0,1)
            m=cv2.resize(m,(w,h),interpolation=cv2.INTER_LINEAR)
            return np.clip(cv2.GaussianBlur(m,(0,0),blur),0,1)
        # Label map of this BiSeNet export: skin=1, eyes=4/5, upper/lower lip=12/13.
        result={'Visage':region(list(range(1,14)),.18,.62,1.0),'Peau':region([1],0.12,0.56,1.0),'Yeux':region([4,5],0.10,0.48,0.55),'Lèvres':region([12,13],0.10,0.48,0.55)}
        q=str(quality or 'precise').lower();rq='very_precise' if q in ('very_precise','tres_precis','très précis') else q
        if rq in ('precise','very_precise'):
            result={name:refine_mask_edges(img,m,rq,'portrait') for name,m in result.items()}
        if progress:progress(1,1)
        return result

    @staticmethod
    def _sam2_image_fp(img):
        x=np.ascontiguousarray(img);h,w=x.shape[:2];sy=max(1,h//64);sx=max(1,w//64)
        sample=np.ascontiguousarray(x[::sy,::sx][:64,:64])
        hh=hashlib.sha256();hh.update(str((x.shape,str(x.dtype))).encode());hh.update(sample.tobytes());return hh.hexdigest()

    @staticmethod
    def _sam2_pick_input(inputs, keywords, fallback_index):
        for item in inputs:
            name=item.name.lower()
            if all(k in name for k in keywords):return item.name
        return inputs[min(fallback_index,len(inputs)-1)].name

    def _sam2_encode(self,img,cancel=None):
        if not self.status().sam2:raise FileNotFoundError('Modèles SAM 2 absents')
        if cancel:cancel.check()
        x=np.clip(img.astype(np.float32),0,1);fp=self._sam2_image_fp(x)
        if fp==self._sam2_fp and self._sam2_embedding is not None:return self._sam2_embedding,self._sam2_original_size
        sess=self._session('sam2_encoder',self.model_dir/'sam2_hiera_tiny.encoder.onnx')
        encoded=linear_to_srgb(x);h,w=encoded.shape[:2]
        inp=sess.get_inputs()[0];shape=inp.shape
        ih=int(shape[2]) if len(shape)>=4 and isinstance(shape[2],int) else 1024
        iw=int(shape[3]) if len(shape)>=4 and isinstance(shape[3],int) else 1024
        resized=cv2.resize(encoded,(iw,ih),interpolation=cv2.INTER_AREA if max(h,w)>max(ih,iw) else cv2.INTER_CUBIC)
        mean=np.array([0.485,0.456,0.406],np.float32);std=np.array([0.229,0.224,0.225],np.float32)
        tensor=((resized-mean)/std).transpose(2,0,1)[None].astype(np.float32)
        outs=self._run('sam2_encoder',sess,None,{inp.name:tensor})
        if len(outs)<3:raise RuntimeError('Sortie encodeur SAM 2 inattendue')
        embedding=(outs[0],outs[1],outs[2],ih,iw)
        self._sam2_fp=fp;self._sam2_embedding=embedding;self._sam2_original_size=(h,w)
        return embedding,(h,w)

    def sam2_mask(self,img,points,progress=None,cancel=None,box=None,prefer_small=False):
        """Promptable object mask.

        points: iterable of (u, v, label), with u/v normalized to the full image
        and label 1=foreground, 0=background. Encoder output is cached so extra
        refinement clicks normally run only the lightweight decoder.
        """
        if not points and box is None:raise ValueError('Un point ou un cadre est nécessaire')
        embedding,(h,w)=self._sam2_encode(img,cancel)
        if cancel:cancel.check()
        high0,high1,image_embed,ih,iw=embedding
        coords=[];labels=[]
        for u,v,label in points:
            coords.append([float(np.clip(u,0,1))*iw,float(np.clip(v,0,1))*ih]);labels.append(float(label))
        if box is not None:
            from .geometry import normalized_crop
            bx,by,bw,bh=normalized_crop(box)
            coords.extend([[bx*iw,by*ih],[(bx+bw)*iw,(by+bh)*ih]]);labels.extend([2.,3.])
        point_coords=np.asarray(coords,np.float32)[None]
        point_labels=np.asarray(labels,np.float32)[None]
        sess=self._session('sam2_decoder',self.model_dir/'sam2_hiera_tiny.decoder.onnx')
        ins=sess.get_inputs();feeds={}
        # Match semantic names when available; fall back to the export's canonical order.
        feeds[self._sam2_pick_input(ins,['image','embed'],0)]=image_embed
        feeds[self._sam2_pick_input(ins,['high','0'],1)]=high0
        feeds[self._sam2_pick_input(ins,['high','1'],2)]=high1
        feeds[self._sam2_pick_input(ins,['point','coord'],3)]=point_coords
        feeds[self._sam2_pick_input(ins,['point','label'],4)]=point_labels
        mask_name=self._sam2_pick_input(ins,['mask','input'],5)
        has_name=self._sam2_pick_input(ins,['has','mask'],6)
        mask_shape=ins[[i.name for i in ins].index(mask_name)].shape
        mh=int(mask_shape[-2]) if len(mask_shape)>=4 and isinstance(mask_shape[-2],int) else ih//4
        mw=int(mask_shape[-1]) if len(mask_shape)>=4 and isinstance(mask_shape[-1],int) else iw//4
        feeds[mask_name]=np.zeros((1,1,mh,mw),np.float32)
        feeds[has_name]=np.zeros((1,),np.float32)
        outs=self._run('sam2_decoder',sess,None,feeds)
        if len(outs)<2:raise RuntimeError('Sortie décodeur SAM 2 inattendue')
        masks=np.asarray(outs[0],np.float32);scores=np.asarray(outs[1],np.float32)
        # Normalize to candidate masks [C,H,W].
        while masks.ndim>4 and masks.shape[0]==1:masks=masks[0]
        if masks.ndim==4:masks=masks[0]
        if masks.ndim==2:masks=masks[None]
        from .object_selection import select_candidate
        # A box already defines the desired scale. Prefer confidence there;
        # selecting the smallest proposal can pick only the object's texture.
        logits=select_candidate(masks,scores,points,prefer_small=prefer_small and box is None)
        soft=1.0/(1.0+np.exp(-np.clip(logits,-30,30)))
        soft=cv2.resize(soft,(w,h),interpolation=cv2.INTER_LINEAR)
        # Keep a soft feathered edge but make the selection visually decisive.
        soft=np.clip((soft-0.42)/0.18,0,1);soft=cv2.GaussianBlur(soft,(0,0),0.7)
        if box is not None:
            from .geometry import crop_bounds
            a,b,c,d=crop_bounds(soft.shape,box)
            soft[:b]=0;soft[d:]=0;soft[:,:a]=0;soft[:,c:]=0
        if progress:progress(1,1)
        return np.clip(soft,0,1)

    @staticmethod
    def _sam2_mask_iou(a,b):
        aa=np.asarray(a,dtype=bool);bb=np.asarray(b,dtype=bool);inter=np.logical_and(aa,bb).sum();union=np.logical_or(aa,bb).sum()
        return float(inter/max(1,union))

    @classmethod
    def _sam2_dedupe_candidates(cls,candidates,iou_threshold=0.82,max_masks=24):
        kept=[]
        for score,logits in sorted(candidates,key=lambda x:x[0],reverse=True):
            binary=np.asarray(logits)>0
            if any(cls._sam2_mask_iou(binary,k[1]>0)>iou_threshold for k in kept):continue
            kept.append((float(score),np.asarray(logits,dtype=np.float32)))
            if len(kept)>=max_masks:break
        return kept

    def sam2_auto_masks(self,img,points_per_side=12,max_masks=24,progress=None,cancel=None):
        """Generate prompt-free object proposals from a regular SAM2 point grid.

        This is intentionally a proposal generator, not semantic object deletion.
        It filters low-confidence/unstable/duplicate masks and returns independent
        editable masks that the user may refine or send to LaMa.
        """
        embedding,(h,w)=self._sam2_encode(img,cancel);high0,high1,image_embed,ih,iw=embedding
        sess=self._session('sam2_decoder',self.model_dir/'sam2_hiera_tiny.decoder.onnx');ins=sess.get_inputs()
        names={
            'embed':self._sam2_pick_input(ins,['image','embed'],0),'high0':self._sam2_pick_input(ins,['high','0'],1),'high1':self._sam2_pick_input(ins,['high','1'],2),
            'coords':self._sam2_pick_input(ins,['point','coord'],3),'labels':self._sam2_pick_input(ins,['point','label'],4),'mask':self._sam2_pick_input(ins,['mask','input'],5),'has':self._sam2_pick_input(ins,['has','mask'],6)}
        mask_shape=ins[[i.name for i in ins].index(names['mask'])].shape;mh=int(mask_shape[-2]) if len(mask_shape)>=4 and isinstance(mask_shape[-2],int) else ih//4;mw=int(mask_shape[-1]) if len(mask_shape)>=4 and isinstance(mask_shape[-1],int) else iw//4
        n=max(4,int(points_per_side));frac=(np.arange(n,dtype=np.float32)+0.5)/n;gx,gy=np.meshgrid(frac,frac);grid=np.stack([gx.ravel(),gy.ravel()],axis=1);candidates=[];batch_size=4;total=len(grid);done=0
        for start in range(0,total,batch_size):
            if cancel:cancel.check()
            g=grid[start:start+batch_size];B=len(g);coords=np.zeros((B,1,2),np.float32);coords[:,0,0]=g[:,0]*iw;coords[:,0,1]=g[:,1]*ih;labs=np.ones((B,1),np.float32)
            feeds={names['embed']:image_embed,names['high0']:high0,names['high1']:high1,names['coords']:coords,names['labels']:labs,names['mask']:np.zeros((B,1,mh,mw),np.float32),names['has']:np.zeros((1,),np.float32)}
            outs=self._run('sam2_decoder',sess,None,feeds);masks=np.asarray(outs[0],np.float32);scores=np.asarray(outs[1],np.float32)
            if masks.ndim==3:masks=masks[:,None]
            if scores.ndim==1:scores=scores[:,None]
            for b in range(min(B,masks.shape[0])):
                sc=scores[b].reshape(-1);j=int(np.argmax(sc)) if sc.size else 0;score=float(sc[j]) if sc.size else 0.0
                if score<0.78:continue
                logit=np.squeeze(masks[b,min(j,masks.shape[1]-1)]).astype(np.float32);binary=logit>0;area=float(binary.mean())
                if area<0.0006 or area>0.82:continue
                high=logit>1.0;low=logit>-1.0;stability=float(np.logical_and(high,low).sum()/max(1,low.sum()))
                if stability<0.88:continue
                candidates.append((score,logit))
            done+=B
            if progress:progress(done,total)
        kept=self._sam2_dedupe_candidates(candidates,0.82,int(max_masks));result=[]
        for score,logit in kept:
            soft=1.0/(1.0+np.exp(-np.clip(logit,-30,30)));soft=np.clip((soft-0.42)/0.18,0,1);soft=cv2.resize(soft,(w,h),interpolation=cv2.INTER_LINEAR);soft=cv2.GaussianBlur(soft,(0,0),0.65)
            result.append({'mask':np.clip(soft,0,1).astype(np.float32),'score':float(score)})
        return result

    def inpaint(self,img,mask,progress=None,cancel=None):
        if cancel:cancel.check()
        if not self.status().inpaint:raise FileNotFoundError('Modèle LaMa absent')
        original=np.asarray(img,np.float32);H,W=original.shape[:2]
        m=cv2.resize(np.asarray(mask,np.float32),(W,H),interpolation=cv2.INTER_LINEAR) if mask.shape!=(H,W) else np.asarray(mask,np.float32)
        m=(m>.05).astype(np.uint8)
        if not np.any(m):return original.copy()
        m=cv2.dilate(m,np.ones((5,5),np.uint8))
        soft=cv2.GaussianBlur(m.astype(np.float32),(0,0),1.2)
        support=soft>1e-4
        soft[~support]=0
        sess=self._session('inpaint',self.model_dir/'inpainting_lama_2025jan.onnx')
        inputs=sess.get_inputs();image_name=next((a.name for a in inputs if 'image' in a.name.lower()),inputs[0].name)
        mask_name=next((a.name for a in inputs if 'mask' in a.name.lower()),inputs[1].name)
        x=linear_to_srgb(np.clip(original,0,1))
        tiles=[(tx,ty) for ty in self._positions(H,512,96) for tx in self._positions(W,512,96) if np.any(support[ty:ty+512,tx:tx+512])]
        accum=np.zeros_like(x);weights=np.zeros((H,W),np.float32)
        feather=np.maximum(np.outer(np.hanning(512),np.hanning(512)),.001).astype(np.float32)
        for index,(tx,ty) in enumerate(tiles,1):
            if cancel:cancel.check()
            xe=min(W,tx+512);ye=min(H,ty+512);patch=x[ty:ye,tx:xe];cm=m[ty:ye,tx:xe];ph,pw=patch.shape[:2]
            canvas=cv2.copyMakeBorder(patch,0,512-ph,0,512-pw,cv2.BORDER_REFLECT_101)
            maskc=cv2.copyMakeBorder(cm,0,512-ph,0,512-pw,cv2.BORDER_CONSTANT,value=0)
            image_blob=np.ascontiguousarray(canvas.transpose(2,0,1)[None],dtype=np.float32)
            mask_blob=np.ascontiguousarray(maskc[None,None],dtype=np.float32)
            prediction=self._run('inpaint',sess,None,{image_name:image_blob,mask_name:mask_blob})[0]
            pred=np.asarray(prediction,np.float32)[0].transpose(1,2,0)
            if pred.max()>2:pred=pred/255.
            if not np.isfinite(pred).all():raise RuntimeError('Le modèle LaMa a produit un résultat non fini')
            weight=feather[:ph,:pw]
            accum[ty:ye,tx:xe]+=np.clip(pred[:ph,:pw],0,1)*weight[...,None]
            weights[ty:ye,tx:xe]+=weight
            if progress:progress(index,max(1,len(tiles)))
        cleaned=srgb_to_linear(accum/np.maximum(weights[...,None],1e-8))
        alpha=soft[...,None]
        return (original*(1-alpha)+cleaned*alpha).astype(np.float32)
