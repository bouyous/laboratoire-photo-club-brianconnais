# PhotoLabPro code reused for the club at the authorizing project owner’s request, 2026-10-13. MIT OR Apache-2.0.
from __future__ import annotations
import numpy as np
import cv2
from .color import linear_to_srgb


def _edge_strength(rgb):
    y=(0.2126*rgb[...,0]+0.7152*rgb[...,1]+0.0722*rgb[...,2]).astype(np.float32)
    gx=cv2.Sobel(y,cv2.CV_32F,1,0,ksize=3);gy=cv2.Sobel(y,cv2.CV_32F,0,1,ksize=3)
    return np.sqrt(gx*gx+gy*gy),y


def refine_mask_edges(img, mask, quality='precise', kind='generic'):
    """Edge-aware mask refinement without inventing new semantic regions.

    It keeps diffusion inside flat areas but resists crossing strong image edges.
    For sky masks, a conservative silhouette guard removes dark, high-frequency
    structures (bare branches, birds, wires) accidentally swallowed by a coarse mask.
    """
    m=np.clip(np.asarray(mask,dtype=np.float32),0,1)
    rgb=linear_to_srgb(np.clip(np.asarray(img,dtype=np.float32),0,1)).astype(np.float32)
    if m.shape!=rgb.shape[:2]:m=cv2.resize(m,(rgb.shape[1],rgb.shape[0]),interpolation=cv2.INTER_LINEAR)
    edge,y=_edge_strength(rgb)
    q=str(quality or 'precise').lower()
    iterations=2 if q=='precise' else 4
    for _ in range(iterations):
        blur=cv2.GaussianBlur(m,(0,0),0.85 if q=='precise' else 0.65)
        barrier=np.exp(-np.clip(edge,0,0.35)*(18.0 if q=='precise' else 26.0)).astype(np.float32)
        alpha=0.45 if q=='precise' else 0.34
        m=np.clip(m*(1.0-alpha*barrier)+blur*(alpha*barrier),0,1)

    # Preserve silhouetted structures against sky. This is deliberately limited
    # to high-gradient darker-than-local pixels to avoid carving normal sky gradients.
    if str(kind).lower() in ('sky','ciel'):
        sigma=max(2.0,min(rgb.shape[:2])/260.0)
        local=cv2.GaussianBlur(y,(0,0),sigma)
        dark=np.clip((local-y-0.025)/0.13,0,1)
        e=np.clip((edge-0.018)/0.10,0,1)
        guard=cv2.GaussianBlur((dark*e).astype(np.float32),(0,0),0.45)
        strength=0.72 if q=='precise' else 0.90
        m=np.clip(m*(1.0-strength*guard),0,1)
    return m.astype(np.float32)


def semantic_prompt_points(mask, positives=6, negatives=8):
    """Generate normalized foreground/background points from a coarse semantic mask."""
    m=np.asarray(mask,dtype=np.float32);h,w=m.shape[:2]
    pos=np.argwhere(m>0.82);neg=np.argwhere(m<0.10)
    def pick(arr,n):
        if len(arr)==0:return []
        idx=np.linspace(0,len(arr)-1,min(n,len(arr)),dtype=int)
        # Sorting by a simple space-filling key gives broad coverage before sampling.
        a=arr[np.argsort(arr[:,0]*w+arr[:,1])]
        return a[idx]
    points=[]
    for y,x in pick(pos,positives):points.append((float(x/max(1,w-1)),float(y/max(1,h-1)),1))
    for y,x in pick(neg,negatives):points.append((float(x/max(1,w-1)),float(y/max(1,h-1)),0))
    return points


def merge_semantic_with_sam(coarse, sam):
    c=np.clip(np.asarray(coarse,dtype=np.float32),0,1);s=np.clip(np.asarray(sam,dtype=np.float32),0,1)
    if s.shape!=c.shape:s=cv2.resize(s,(c.shape[1],c.shape[0]),interpolation=cv2.INTER_LINEAR)
    cb=c>0.5;sb=s>0.5;inter=np.logical_and(cb,sb).sum();union=np.logical_or(cb,sb).sum();iou=float(inter/max(1,union))
    ar=float(sb.mean()/max(1e-6,cb.mean()))
    # Reject an obviously unrelated SAM proposal rather than ruining a valid coarse mask.
    if iou<0.32 or ar<0.35 or ar>2.4:return c
    return np.clip(0.22*c+0.78*s,0,1).astype(np.float32)
