# PhotoLabPro code reused for the club at the authorizing project owner’s request, 2026-10-13. MIT OR Apache-2.0.
from __future__ import annotations
import numpy as np


def srgb_to_linear(img: np.ndarray) -> np.ndarray:
    """Convert normalized sRGB transfer values to linear-light float32."""
    x=np.clip(np.asarray(img,dtype=np.float32),0,1)
    return np.where(x<=0.04045,x/12.92,((x+0.055)/1.055)**2.4).astype(np.float32)


def linear_to_srgb(img: np.ndarray) -> np.ndarray:
    """Convert normalized linear-light RGB to sRGB transfer values."""
    x=np.clip(np.asarray(img,dtype=np.float32),0,1)
    return np.where(x<=0.0031308,12.92*x,1.055*np.power(x,1/2.4)-0.055).astype(np.float32)
