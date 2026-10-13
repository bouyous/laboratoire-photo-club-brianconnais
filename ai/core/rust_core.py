# PhotoLabPro code reused for the club at the authorizing project owner’s request, 2026-10-13. MIT OR Apache-2.0.
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import ctypes
import os
import platform
import sys
import threading
import numpy as np

ABI_VERSION = 1
_LOCK = threading.Lock()
_DLL = None
_LOAD_ATTEMPTED = False
_LOAD_ERROR = ''
_LOAD_PATH = None


@dataclass(frozen=True)
class RustCoreStatus:
    available: bool
    abi: int
    path: str
    error: str


def _library_name() -> str:
    system = platform.system()
    if system == 'Windows':
        return 'photolab_core.dll'
    if system == 'Darwin':
        return 'libphotolab_core.dylib'
    return 'libphotolab_core.so'


def _candidate_paths():
    name = _library_name()
    env = os.environ.get('PLP_RUST_CORE', '').strip()
    if env:
        yield Path(env)

    here = Path(__file__).resolve().parent.parent
    yield here / 'native' / 'bin' / name

    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        base = Path(meipass)
        yield base / 'native' / 'bin' / name
        yield base / name

    exe = Path(sys.executable).resolve().parent
    yield exe / 'native' / 'bin' / name
    yield exe / name




def _configure_nikon(dll):
    """Configure optional Nikon bridge symbols added in PhotoLab 4.13.7.

    Older photolab_core.dll builds remain usable for the normal pixel pipeline;
    the Nikon bridge is simply unavailable until the native core is rebuilt.
    """
    try:
        decode = dll.plp_nikon_decode_rgb8
        free = dll.plp_nikon_free_buffer
    except AttributeError:
        return False
    decode.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    decode.restype = ctypes.c_int32
    free.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    free.restype = None
    return True

def _configure(dll):
    dll.plp_core_abi_version.argtypes = []
    dll.plp_core_abi_version.restype = ctypes.c_uint32

    dll.plp_apply_fast_rgb.argtypes = [
        ctypes.POINTER(ctypes.c_float), ctypes.c_size_t,
        ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ctypes.POINTER(ctypes.c_float), ctypes.c_size_t,
        ctypes.c_int,
        ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ctypes.c_int,
    ]
    dll.plp_apply_fast_rgb.restype = ctypes.c_int

    dll.plp_tile_positions.argtypes = [
        ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t), ctypes.c_size_t,
    ]
    dll.plp_tile_positions.restype = ctypes.c_size_t
    try:
        dll.plp_display_rgb8.argtypes=[ctypes.POINTER(ctypes.c_float),ctypes.c_size_t,ctypes.POINTER(ctypes.c_uint8),ctypes.c_size_t,ctypes.POINTER(ctypes.c_uint8)]
        dll.plp_display_rgb8.restype=ctypes.c_int
    except AttributeError:pass  # Older ABI-1 libraries retain Python display conversion.
    _configure_nikon(dll)


def _load():
    global _DLL, _LOAD_ATTEMPTED, _LOAD_ERROR, _LOAD_PATH
    if _LOAD_ATTEMPTED:
        return _DLL
    with _LOCK:
        if _LOAD_ATTEMPTED:
            return _DLL
        _LOAD_ATTEMPTED = True
        errors = []
        for path in _candidate_paths():
            try:
                if not path.exists():
                    continue
                dll = ctypes.CDLL(str(path))
                _configure(dll)
                abi = int(dll.plp_core_abi_version())
                if abi != ABI_VERSION:
                    errors.append(f'{path}: ABI {abi}, attendu {ABI_VERSION}')
                    continue
                _DLL = dll
                _LOAD_PATH = path
                _LOAD_ERROR = ''
                return _DLL
            except Exception as exc:
                errors.append(f'{path}: {exc}')
        _LOAD_ERROR = ' | '.join(errors) if errors else 'DLL Rust non compilée / introuvable'
        return None


def status() -> RustCoreStatus:
    dll = _load()
    abi = 0
    if dll is not None:
        try:
            abi = int(dll.plp_core_abi_version())
        except Exception:
            abi = 0
    return RustCoreStatus(bool(dll), abi, str(_LOAD_PATH or ''), _LOAD_ERROR)


def available() -> bool:
    return _load() is not None


def display_rgb8(image,table):
    dll=_load()
    if dll is None or not hasattr(dll,'plp_display_rgb8'):return None
    x=np.asarray(image)
    # Avoid a hidden full-frame conversion/copy for unsupported layouts.
    if x.dtype!=np.float32 or not x.flags.c_contiguous or not x.flags.aligned:return None
    lut=np.asarray(table)
    if lut.dtype!=np.uint8 or lut.shape!=(65536,) or not lut.flags.c_contiguous:return None
    result=np.empty(x.shape,dtype=np.uint8)
    rc=dll.plp_display_rgb8(x.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),x.size,
        lut.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),lut.size,
        result.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)))
    return result if rc==0 else None


def reset_loader_for_tests():
    global _DLL, _LOAD_ATTEMPTED, _LOAD_ERROR, _LOAD_PATH
    with _LOCK:
        _DLL = None
        _LOAD_ATTEMPTED = False
        _LOAD_ERROR = ''
        _LOAD_PATH = None


def apply_fast_base(
    img: np.ndarray,
    *,
    exposure: float,
    contrast: float,
    highlights: float,
    shadows: float,
    lowlights: float,
    whites: float,
    blacks: float,
    saturation: float,
    gains,
    curve,
    black_white: bool,
    bw_mix,
    preserve_headroom: bool,
):
    """Run the phase-1 native pixel pipeline, returning None on fallback.

    The bridge never modifies the caller's image. Any native error results in a
    clean Python fallback so a missing/incompatible DLL cannot make PhotoLab unusable.
    """
    dll = _load()
    if dll is None:
        return None
    try:
        x = np.asarray(img, dtype=np.float32)
        if x.ndim != 3 or x.shape[2] != 3:
            return None
        out = np.ascontiguousarray(x).copy()
        curve_arr = np.ascontiguousarray(np.asarray(curve or (), dtype=np.float32).reshape(-1))
        gains_arr = np.asarray(gains, dtype=np.float32).reshape(-1)
        mix_arr = np.asarray(bw_mix, dtype=np.float32).reshape(-1)
        if gains_arr.size != 3 or mix_arr.size != 3:
            return None
        curve_ptr = curve_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_float)) if curve_arr.size else ctypes.POINTER(ctypes.c_float)()
        rc = int(dll.plp_apply_fast_rgb(
            out.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            ctypes.c_size_t(out.shape[0] * out.shape[1]),
            ctypes.c_float(float(exposure)), ctypes.c_float(float(contrast)),
            ctypes.c_float(float(highlights)), ctypes.c_float(float(shadows)),
            ctypes.c_float(float(lowlights)), ctypes.c_float(float(whites)),
            ctypes.c_float(float(blacks)), ctypes.c_float(float(saturation)),
            ctypes.c_float(float(gains_arr[0])), ctypes.c_float(float(gains_arr[1])), ctypes.c_float(float(gains_arr[2])),
            curve_ptr, ctypes.c_size_t(curve_arr.size),
            ctypes.c_int(1 if black_white else 0),
            ctypes.c_float(float(mix_arr[0])), ctypes.c_float(float(mix_arr[1])), ctypes.c_float(float(mix_arr[2])),
            ctypes.c_int(1 if preserve_headroom else 0),
        ))
        if rc != 0:
            return None
        return out
    except Exception:
        return None


def tile_positions(size: int, tile: int, overlap: int):
    """Native tile geometry with a Python fallback-safe return value."""
    dll = _load()
    if dll is None:
        return None
    try:
        size = max(0, int(size)); tile = max(0, int(tile)); overlap = max(0, int(overlap))
        n = int(dll.plp_tile_positions(size, tile, overlap, ctypes.POINTER(ctypes.c_size_t)(), 0))
        if n <= 0:
            return []
        buf = (ctypes.c_size_t * n)()
        written = int(dll.plp_tile_positions(size, tile, overlap, buf, n))
        if written != n:
            return None
        return [int(buf[i]) for i in range(n)]
    except Exception:
        return None

def nikon_decode_rgb8(dll_path: str | Path, nef_path: str | Path):
    """Decode a Nikon NEF through the native Rust SDK bridge.

    Returns ``(array, diagnostic)``. ``array`` is uint8 RGB on success and
    ``None`` otherwise. The diagnostic intentionally includes the native stage
    and Nikon status code so a user screenshot is enough to locate a failure.
    """
    if platform.system() != 'Windows':
        return None, 'pont Nikon Rust: plateforme non-Windows'
    dll = _load()
    if dll is None:
        return None, 'pont Nikon Rust indisponible: ' + (_LOAD_ERROR or 'photolab_core.dll absent')
    if not _configure_nikon(dll):
        return None, 'pont Nikon Rust absent de photolab_core.dll (recompiler PhotoLab)'

    out_ptr = ctypes.c_void_p()
    out_len = ctypes.c_size_t(0)
    out_w = ctypes.c_uint32(0)
    out_h = ctypes.c_uint32(0)
    stage = ctypes.c_uint32(0)
    nikon_code = ctypes.c_uint32(0)
    try:
        rc = int(dll.plp_nikon_decode_rgb8(
            str(Path(dll_path)).encode('utf-8'),
            str(Path(nef_path)).encode('utf-8'),
            ctypes.byref(out_ptr), ctypes.byref(out_len),
            ctypes.byref(out_w), ctypes.byref(out_h),
            ctypes.byref(stage), ctypes.byref(nikon_code),
        ))
        if rc != 0:
            return None, (
                f'pont Nikon Rust rc={rc}, stage={int(stage.value)}, '
                f'code=0x{int(nikon_code.value):04X}'
            )
        w = int(out_w.value); h = int(out_h.value); n = int(out_len.value)
        expected = w * h * 3
        if not out_ptr.value or w <= 0 or h <= 0 or n != expected:
            return None, f'pont Nikon Rust: sortie invalide {w}×{h}, {n} octets (attendu {expected})'
        raw = ctypes.string_at(out_ptr, n)
        arr = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3).copy()
        return arr, f'pont Nikon Rust OK: {w}×{h} RGB8'
    except Exception as exc:
        return None, f'pont Nikon Rust: {exc}'
    finally:
        if out_ptr.value and out_len.value:
            try:
                dll.plp_nikon_free_buffer(out_ptr, out_len)
            except Exception:
                pass
