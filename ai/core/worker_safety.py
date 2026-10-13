# PhotoLabPro code reused for the club at the authorizing project owner’s request, 2026-10-13. MIT OR Apache-2.0.
"""Child-only native crash handling: let the parent report/retry the failure."""
import os


def configure_worker():
    if os.name=='nt':
        import ctypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.GetErrorMode.restype=ctypes.c_uint
        kernel.SetErrorMode.argtypes=[ctypes.c_uint]
        kernel.SetErrorMode(kernel.GetErrorMode()|0x0001|0x0002)
        try:
            wer=ctypes.WinDLL('wer');wer.WerSetFlags(0x0020)
        except (OSError,AttributeError):pass
    # The parent redirects stderr to the per-job log; keep the Python stacks
    # on access violations instead of losing all context with the process.
    try:
        import faulthandler
        faulthandler.enable(all_threads=True)
    except (OSError,RuntimeError,AttributeError):pass
