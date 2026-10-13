# PhotoLabPro code reused for the club at the authorizing project owner’s request, 2026-10-13. MIT OR Apache-2.0.
"""Resolve ambiguous SAM proposals against explicit user prompts."""
import numpy as np
import cv2
from .geometry import crop_bounds,normalized_crop


def select_candidate(masks,scores,points,prefer_small=False):
    masks=np.asarray(masks,np.float32);scores=np.asarray(scores).reshape(-1)
    valid=[]
    for i,logits in enumerate(masks):
        if not np.isfinite(logits).all():continue
        h,w=logits.shape;binary=logits>0
        positives=[];violations=0
        for u,v,label in points:
            if int(label) not in (0,1):continue
            x=min(w-1,max(0,int(u*w)));y=min(h-1,max(0,int(v*h)))
            hit=bool(binary[y,x]);violations+=int(hit!=(int(label)==1))
            if int(label)==1:positives.append((x,y))
        if violations or not binary.any():continue
        # Keep only components actually pointed at; detached areas are not selected.
        if positives:
            _,labels=cv2.connectedComponents(binary.astype(np.uint8),connectivity=8)
            keep={int(labels[y,x]) for x,y in positives}-{0}
            binary=np.isin(labels,list(keep));logits=np.where(binary,logits,-30.)
        score=float(scores[i]) if i<len(scores) and np.isfinite(scores[i]) else 0.
        stability=float((logits>1).sum()/max(1,(logits>-1).sum()))
        valid.append((score,int(binary.sum()),logits,stability))
    if not valid:raise ValueError('Aucune proposition ne respecte les points. Encadrez l’objet ou recommencez avec Nouvel objet.')
    best=max(item[0] for item in valid)
    # Size is a tie-breaker among plausible proposals, not a replacement for confidence.
    eligible=[item for item in valid if item[0]>=best-.12] if prefer_small else valid
    if prefer_small:
        # Reject a fragmented/uncertain texture proposal when a stable object
        # with comparable confidence exists.
        stable=max(item[3] for item in eligible)
        eligible=[item for item in eligible if item[3]>=stable-.1]
    chosen=min(eligible,key=lambda item:(item[1],-item[0])) if prefer_small else max(eligible,key=lambda item:item[0])
    return chosen[2]


def object_context(image,box):
    """Extract original-resolution detail around the user box with context."""
    rect=normalized_crop(box)
    if rect is None:raise ValueError('Encadrez un objet dans la photo.')
    x,y,w,h=rect
    left=max(0.,x-w*.5);top=max(0.,y-h*.5)
    right=min(1.,x+w*1.5);bottom=min(1.,y+h*1.5)
    x0,y0,x1,y1=crop_bounds(image.shape,(left,top,right-left,bottom-top))
    ih,iw=image.shape[:2];region=(x0/iw,y0/ih,(x1-x0)/iw,(y1-y0)/ih)
    rx,ry,rw,rh=region
    local=((x-rx)/rw,(y-ry)/rh,w/rw,h/rh)
    roi=image[y0:y1,x0:x1]
    if max(roi.shape[:2])>1536:
        scale=1536/max(roi.shape[:2]);roi=cv2.resize(roi,(max(1,round(roi.shape[1]*scale)),max(1,round(roi.shape[0]*scale))),interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(roi),region,local


def place_region_mask(mask,shape,region,box):
    result=np.zeros(shape[:2],np.float32)
    x0,y0,x1,y1=crop_bounds(shape,region)
    result[y0:y1,x0:x1]=cv2.resize(mask,(x1-x0,y1-y0),interpolation=cv2.INTER_LINEAR)
    # Interpolation must never spread the selection outside the user's enclosure.
    a,b,c,d=crop_bounds(shape,box)
    result[:b]=0;result[d:]=0;result[:,:a]=0;result[:,c:]=0
    return result
