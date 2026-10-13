# PhotoLabPro code reused for the club at the authorizing project owner’s request, 2026-10-13. MIT OR Apache-2.0.
"""Normalized non-destructive crop, shared by preview and full-size export."""
import math


def normalized_crop(rect):
    if rect is None:return None
    try:
        x,y,w,h=map(float,rect)
        if not all(math.isfinite(v) for v in (x,y,w,h)):return None
        x=max(0.,min(.999,x));y=max(0.,min(.999,y))
        w=max(.001,min(1.-x,w));h=max(.001,min(1.-y,h))
        return (x,y,w,h)
    except (ValueError,TypeError):return None


def crop_bounds(shape,rect):
    h,w=shape[:2];r=normalized_crop(rect)
    if r is None:return 0,0,w,h
    x,y,rw,rh=r;x0=min(w-1,round(x*w));y0=min(h-1,round(y*h))
    return x0,y0,max(x0+1,min(w,round((x+rw)*w))),max(y0+1,min(h,round((y+rh)*h)))
