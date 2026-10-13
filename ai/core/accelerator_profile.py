# PhotoLabPro code reused for the club at the authorizing project owner’s request, 2026-10-13. MIT OR Apache-2.0.
from __future__ import annotations
import json, time
from pathlib import Path
from .paths import app_data_dir

PROFILE_VERSION = 3


def profile_path() -> Path:
    return app_data_dir() / 'accelerator_profile.json'


def _load():
    try:
        raw=json.loads(profile_path().read_text(encoding='utf-8'))
        if not isinstance(raw,dict):raise ValueError
    except Exception:
        raw={'version':PROFILE_VERSION,'devices':{}}
    raw.setdefault('devices',{})
    raw['version']=PROFILE_VERSION
    return raw


def _key(provider:str,gpu_index:int=0):
    return f'{str(provider)}|{max(0,int(gpu_index))}'


def safe_tile(provider:str,gpu_index:int=0) -> int:
    rec=_load().get('devices',{}).get(_key(provider,gpu_index),{})
    try:return max(0,int(rec.get('safe_tile',0) or 0))
    except Exception:return 0


def record_probe(provider:str,gpu_index:int,safe_tile_value:int,seconds:float|None=None,details=None,repeats:int=1):
    data=_load();devices=data.setdefault('devices',{});k=_key(provider,gpu_index)
    devices[k]={
        'provider':str(provider),'gpu_index':max(0,int(gpu_index)),
        'safe_tile':max(0,int(safe_tile_value)),
        'seconds':None if seconds is None else float(seconds),
        'updated_at':time.time(),'details':details or {},'repeats':max(1,int(repeats)),
    }
    p=profile_path();p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')



def probe_record(provider:str,gpu_index:int=0) -> dict:
    return dict(_load().get('devices',{}).get(_key(provider,gpu_index),{}) or {})

def stress_verified(provider:str,gpu_index:int=0,min_repeats:int=8) -> bool:
    rec=probe_record(provider,gpu_index)
    try:
        mode=str((rec.get('details') or {}).get('mode') or '')
        return mode in ('hybrid','strict_v3') and int(rec.get('safe_tile',0) or 0)>0 and int(rec.get('repeats',0) or 0)>=int(min_repeats)
    except Exception:
        return False

def clear_profile(provider:str|None=None,gpu_index:int=0):
    p=profile_path()
    if provider is None:
        try:p.unlink()
        except FileNotFoundError:pass
        return
    data=_load();data.setdefault('devices',{}).pop(_key(provider,gpu_index),None)
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
