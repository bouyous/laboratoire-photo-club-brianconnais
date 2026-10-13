# PhotoLabPro code reused for the club at the authorizing project owner’s request, 2026-10-13. MIT OR Apache-2.0.
from __future__ import annotations
from dataclasses import dataclass, asdict
import math
import numpy as np
import cv2
from .color import linear_to_srgb


@dataclass
class NoiseAnalysis:
    score: float
    luminance_sigma: float
    chroma_sigma: float
    shadow_fraction: float
    median_luminance: float
    iso: int | None
    recommended_mode: str
    reason: str

    def to_dict(self):
        return asdict(self)


def _robust_sigma(values: np.ndarray) -> float:
    v=np.asarray(values,dtype=np.float32).reshape(-1)
    if v.size<64:return 0.0
    med=float(np.median(v));mad=float(np.median(np.abs(v-med)))
    return max(0.0,mad/0.67448975)


def analyze_noise(img, iso: int|None=None) -> NoiseAnalysis:
    """Estimate visible noise without using the EXIF ISO as the sole criterion.

    The estimate is intentionally conservative. It measures high-frequency residuals
    only in relatively low-texture areas, estimates chroma noise separately, then
    adds smaller penalties for deep shadows and very high ISO metadata.
    """
    x=np.asarray(img,dtype=np.float32)
    if x.ndim!=3 or x.shape[2]<3:raise ValueError('Image RGB attendue pour analyser le bruit')
    x=linear_to_srgb(np.clip(x[...,:3],0,1)).astype(np.float32)
    h,w=x.shape[:2]
    scale=min(1.0,1024.0/max(1,h,w))
    if scale<1.0:x=cv2.resize(x,(max(64,int(round(w*scale))),max(64,int(round(h*scale)))),interpolation=cv2.INTER_AREA)
    y=(0.2126*x[...,0]+0.7152*x[...,1]+0.0722*x[...,2]).astype(np.float32)
    smooth=cv2.GaussianBlur(y,(0,0),1.15)
    residual=y-smooth
    gx=cv2.Sobel(y,cv2.CV_32F,1,0,ksize=3);gy=cv2.Sobel(y,cv2.CV_32F,0,1,ksize=3)
    grad=np.sqrt(gx*gx+gy*gy)
    gthr=float(np.percentile(grad,38.0))
    usable=(grad<=max(0.008,gthr))&(y>0.025)&(y<0.92)
    if int(usable.sum())<512:usable=(y>0.025)&(y<0.92)
    lum_sigma=_robust_sigma(residual[usable])

    # Chroma residuals: channel differences reject most luminance structure.
    rg=(x[...,0]-x[...,1]).astype(np.float32);bg=(x[...,2]-x[...,1]).astype(np.float32)
    rg_res=rg-cv2.GaussianBlur(rg,(0,0),1.15);bg_res=bg-cv2.GaussianBlur(bg,(0,0),1.15)
    chroma_sigma=0.5*(_robust_sigma(rg_res[usable])+_robust_sigma(bg_res[usable]))
    shadow_fraction=float(np.mean(y<0.12));median_l=float(np.median(y))

    # Convert measured noise to a 0..100 severity scale. Visible real-photo noise
    # often falls in roughly 0.004..0.06 in normalized sRGB after this estimator.
    lum_score=float(np.clip((lum_sigma-0.0025)/0.052,0,1))*52.0
    chroma_score=float(np.clip((chroma_sigma-0.0030)/0.060,0,1))*22.0
    shadow_score=float(np.clip((shadow_fraction-0.18)/0.58,0,1))*12.0
    iso_score=0.0
    iso_i=None
    try:
        if iso is not None and int(iso)>0:
            iso_i=int(iso);iso_score=float(np.clip((math.log2(max(100,iso_i)/100.0)-3.0)/7.0,0,1))*14.0
    except Exception:iso_i=None
    score=float(np.clip(lum_score+chroma_score+shadow_score+iso_score,0,100))

    if score<30:
        mode='comfort';reason='bruit léger : priorité à la conservation du détail'
    elif score<68:
        mode='quality';reason='bruit réel modéré/fort : modèle fidèle généraliste'
    else:
        mode='extreme';reason='bruit sévère : fusion multi-passes haute qualité'
    if iso_i is not None and iso_i>=51200 and mode!='extreme':
        mode='extreme';reason='ISO très élevé + analyse d’image : traitement extrême recommandé'
    elif iso_i is not None and iso_i>=16000 and mode=='comfort':
        mode='quality';reason='ISO élevé : traitement qualité recommandé malgré un bruit mesuré modéré'
    return NoiseAnalysis(score,lum_sigma,chroma_sigma,shadow_fraction,median_l,iso_i,mode,reason)


def local_noise_weight(img) -> np.ndarray:
    """Return a smooth 0..1 map: 1 where aggressive cleanup is relatively safe/useful."""
    x=linear_to_srgb(np.clip(np.asarray(img,dtype=np.float32),0,1)).astype(np.float32)
    y=(0.2126*x[...,0]+0.7152*x[...,1]+0.0722*x[...,2]).astype(np.float32)
    smooth=cv2.GaussianBlur(y,(0,0),1.25);res=np.abs(y-smooth)
    noise=cv2.GaussianBlur(res,(0,0),3.0)
    gx=cv2.Sobel(y,cv2.CV_32F,1,0,ksize=3);gy=cv2.Sobel(y,cv2.CV_32F,0,1,ksize=3)
    detail=cv2.GaussianBlur(np.sqrt(gx*gx+gy*gy),(0,0),1.0)
    n=np.clip((noise-0.004)/0.040,0,1)
    d=np.clip((detail-0.018)/0.12,0,1)
    shadow=np.clip((0.34-y)/0.30,0,1)
    w=np.clip(0.18+0.62*n+0.18*shadow-0.42*d,0.08,0.92)
    return cv2.GaussianBlur(w.astype(np.float32),(0,0),1.0)


def recommended_strength(analysis):
    """Cap automatic denoising on clean images, regardless of ISO alone."""
    return float(np.clip(.12+analysis.score*.014,.12,.90))
