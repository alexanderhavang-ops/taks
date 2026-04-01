from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RUNTIME_ROOT = Path("/opt/tak/tools/martine")
RUNTIME_CONF_DIR = RUNTIME_ROOT / "conf.d"
RUNTIME_CONFMETA_DIR = RUNTIME_ROOT / "confmeta"
RUNTIME_LEGACY_CONF = RUNTIME_ROOT / "martine.conf"

SOURCE_ROOT = Path("/opt/taks/martine")
SOURCE_CONF_DIR = SOURCE_ROOT / "conf.d"
SOURCE_CONFMETA_DIR = SOURCE_ROOT / "confmeta"
SOURCE_LEGACY_CONF = SOURCE_ROOT / "conf.d" / "martine-server.conf.template"


def _parse_kv_text(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('[') and line.endswith(']'):
            continue
        if '=' not in line:
            continue
        k, v = line.split('=', 1)
        k = k.strip()
        v = v.strip()
        if k:
            out[k] = v
    return out


def _read_kv_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return _parse_kv_text(path.read_text(encoding='utf-8'))


def _load_dir_kv(dir_path: Path) -> tuple[dict[str, str], dict[str, str]]:
    merged: dict[str, str] = {}
    owners: dict[str, str] = {}
    if not dir_path.exists() or not dir_path.is_dir():
        return merged, owners
    for p in sorted(dir_path.glob('*.conf')):
        kv = _read_kv_file(p)
        component = p.stem
        for k, v in kv.items():
            merged[k] = v
            owners[k] = component
    return merged, owners


def _load_meta_dir(dir_path: Path) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    if not dir_path.exists() or not dir_path.is_dir():
        return merged
    for p in sorted(dir_path.glob('*.json')):
        try:
            obj = json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            continue
        component = str(obj.get('component') or p.stem)
        fields = obj.get('fields')
        if not isinstance(fields, dict):
            continue
        for name, meta in fields.items():
            x = dict(meta) if isinstance(meta, dict) else {}
            x.setdefault('name', str(name))
            x.setdefault('component', component)
            merged[str(name)] = x
    return merged


@dataclass
class KVView:
    values: dict[str, str]
    owners: dict[str, str]
    meta: dict[str, dict[str, Any]]
    source_kind: str
    root_path: str
    _loaded_from: str = ''

    def get(self, key: str, default: str = '') -> str:
        return self.values.get(str(key), default)


def load_runtime_config_view() -> KVView:
    values, owners = _load_dir_kv(RUNTIME_CONF_DIR)
    source_kind = 'conf.d'
    root_path = str(RUNTIME_CONF_DIR)
    if not values:
        values = _read_kv_file(RUNTIME_LEGACY_CONF)
        owners = {k: 'legacy' for k in values.keys()}
        source_kind = 'legacy'
        root_path = str(RUNTIME_LEGACY_CONF)
    meta = _load_meta_dir(RUNTIME_CONFMETA_DIR)
    return KVView(values=values, owners=owners, meta=meta, source_kind=source_kind, root_path=root_path, _loaded_from=root_path)
