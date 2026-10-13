# PhotoLabPro code reused for the club at the authorizing project owner’s request, 2026-10-13. MIT OR Apache-2.0.
from __future__ import annotations
from pathlib import Path
import os, sys

APP_NAME = 'PhotoLabPro'

def app_data_dir() -> Path:
    override = os.environ.get('PHOTOLAB_DATA_DIR')
    if override:
        root = Path(override)
    elif os.name == 'nt':
        root = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / APP_NAME
    elif sys.platform == 'darwin':
        root = Path.home() / 'Library' / 'Application Support' / APP_NAME
    else:
        root = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / APP_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root

def models_dir() -> Path:
    p = Path(os.environ['PHOTOLAB_MODELS_DIR']) if os.environ.get('PHOTOLAB_MODELS_DIR') else app_data_dir() / 'models'
    p.mkdir(parents=True, exist_ok=True); return p

def cache_dir() -> Path:
    p = app_data_dir() / 'cache'; p.mkdir(parents=True, exist_ok=True); return p

def history_dir() -> Path:
    p = cache_dir() / 'history'; p.mkdir(parents=True, exist_ok=True); return p


def presets_dir() -> Path:
    p = app_data_dir() / 'presets'; p.mkdir(parents=True, exist_ok=True); return p

def catalog_dir() -> Path:
    p = app_data_dir() / 'catalog'; p.mkdir(parents=True, exist_ok=True); return p

def catalog_proxy_dir() -> Path:
    p = catalog_dir() / 'proxies'; p.mkdir(parents=True, exist_ok=True); return p

def catalog_db_path() -> Path:
    return catalog_dir() / 'catalog.sqlite3'
