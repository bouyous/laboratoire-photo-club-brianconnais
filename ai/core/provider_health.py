# PhotoLabPro code reused for the club at the authorizing project owner’s request, 2026-10-13. MIT OR Apache-2.0.
from __future__ import annotations
import json, time
from pathlib import Path
from .paths import app_data_dir

HEALTH_VERSION = 3
LEGACY_SOFT_REASONS = (
    'Échec du micro-benchmark SCUNet',
    'Echec du micro-benchmark SCUNet',
    'Benchmark SCUNet indisponible',
    'Crash natif pendant benchmark',
)


def health_path() -> Path:
    return app_data_dir() / 'provider_health.json'


def _migrate(data):
    if not isinstance(data,dict):
        data={'version':HEALTH_VERSION,'blocked':{}}
    data.setdefault('blocked',{})
    # v4.9.x could quarantine DirectML merely because the SCUNet model was not
    # installed yet or its micro-benchmark failed cleanly. That is not evidence
    # of a GPU/driver crash. Remove those stale soft blocks automatically.
    cleaned={}
    for provider,rec in dict(data.get('blocked') or {}).items():
        reason=str((rec or {}).get('reason',''))
        if any(reason.startswith(x) for x in LEGACY_SOFT_REASONS):
            continue
        cleaned[provider]=rec
    data['blocked']=cleaned
    data['version']=HEALTH_VERSION
    return data


def load_health():
    p=health_path()
    try:
        raw=json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        raw={'version':HEALTH_VERSION,'blocked':{}}
    data=_migrate(raw)
    # Persist migration best-effort so an old false quarantine does not return.
    try:
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    except Exception:
        pass
    return data


def blocked_providers():
    return set(load_health().get('blocked',{}).keys())


def block_provider(provider:str, reason:str='native crash'):
    if not provider or provider=='CPUExecutionProvider':return
    data=load_health();data.setdefault('blocked',{})[provider]={'reason':str(reason)[:500],'time':time.time()}
    p=health_path();p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8');tmp.replace(p)


def unblock_provider(provider:str):
    if not provider:return False
    data=load_health();blocked=data.setdefault('blocked',{})
    existed=provider in blocked
    blocked.pop(provider,None)
    if existed:
        p=health_path();p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    return existed


def reset_provider_health():
    p=health_path()
    try:p.unlink()
    except FileNotFoundError:pass


def health_summary():
    data=load_health().get('blocked',{})
    return [(k,v.get('reason','')) for k,v in data.items()]
