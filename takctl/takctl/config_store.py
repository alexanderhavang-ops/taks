from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RUNTIME_ROOT = Path("/opt/tak/tools/takctl")
RUNTIME_CONF_DIR = RUNTIME_ROOT / "conf.d"
RUNTIME_SECRETS_DIR = RUNTIME_ROOT / "secrets.d"
RUNTIME_CONFMETA_DIR = RUNTIME_ROOT / "confmeta"
RUNTIME_LEGACY_CONF = RUNTIME_ROOT / "takctl.conf"
RUNTIME_LEGACY_SECRETS = RUNTIME_ROOT / "secrets.conf"

DEFAULT_CONFIG_PATH = str(RUNTIME_LEGACY_CONF)
DEFAULT_SECRETS_PATH = str(RUNTIME_LEGACY_SECRETS)

SOURCE_ROOT = Path("/opt/taks/takctl")
SOURCE_CONF_DIR = SOURCE_ROOT / "conf.d"
SOURCE_SECRETS_DIR = SOURCE_ROOT / "secrets.d"
SOURCE_CONFMETA_DIR = SOURCE_ROOT / "confmeta"
SOURCE_LEGACY_CONF = SOURCE_ROOT / "takctl.conf.template"
SOURCE_LEGACY_SECRETS = SOURCE_ROOT / "secrets.conf.template"


def _render_conf(section: str, kv: dict[str, str]) -> str:
    lines = [f"[{section}]", "# written by takctl.config_store", ""]
    for k in sorted(kv.keys()):
        lines.append(f"{k} = {kv.get(k, '')}")
    lines.append("")
    return "\n".join(lines)


def _parse_kv_text(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k:
            out[k] = v
    return out


def _read_kv_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return _parse_kv_text(path.read_text(encoding="utf-8"))


def _load_dir_kv(dir_path: Path) -> tuple[dict[str, str], dict[str, str]]:
    merged: dict[str, str] = {}
    owners: dict[str, str] = {}

    if not dir_path.exists() or not dir_path.is_dir():
        return merged, owners

    for p in sorted(dir_path.glob("*.conf")):
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

    for p in sorted(dir_path.glob("*.json")):
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue

        component = str(obj.get("component") or p.stem)
        fields = obj.get("fields")
        if not isinstance(fields, dict):
            continue

        for name, meta in fields.items():
            if not isinstance(meta, dict):
                meta = {}
            x = dict(meta)
            x.setdefault("name", str(name))
            x.setdefault("component", component)
            merged[str(name)] = x

    return merged


@dataclass
class KVView:
    values: dict[str, str]
    owners: dict[str, str]
    meta: dict[str, dict[str, Any]]
    source_kind: str
    root_path: str
    _loaded_from: str = ""
    _secrets_loaded_from: str = ""

    def get(self, key: str, default: str = "") -> str:
        return self.values.get(str(key), default)

    def set(self, key: str, value: Any, *, component: str | None = None) -> None:
        k = str(key)
        self.values[k] = "" if value is None else str(value)
        if component:
            self.owners[k] = component
        elif k not in self.owners:
            self.owners[k] = str((self.meta.get(k) or {}).get("component") or "other")

    def keys(self) -> list[str]:
        return sorted(self.values.keys())

    def items(self) -> list[tuple[str, str]]:
        return [(k, self.values[k]) for k in sorted(self.values.keys())]

    def component_for(self, key: str) -> str:
        k = str(key)
        if k in self.owners:
            return self.owners[k]
        m = self.meta.get(k) or {}
        return str(m.get("component") or "other")

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name in self.values:
            return self.values[name]
        raise AttributeError(name)

    def __contains__(self, key: object) -> bool:
        if key is None:
            return False
        return str(key) in self.values


def load_runtime_config_view() -> KVView:
    values, owners = _load_dir_kv(RUNTIME_CONF_DIR)
    source_kind = "conf.d"
    root_path = str(RUNTIME_CONF_DIR)

    if not values:
        values = _read_kv_file(RUNTIME_LEGACY_CONF)
        owners = {k: "legacy" for k in values.keys()}
        source_kind = "legacy"
        root_path = str(RUNTIME_LEGACY_CONF)

    meta = _load_meta_dir(RUNTIME_CONFMETA_DIR)
    return KVView(values=values, owners=owners, meta=meta, source_kind=source_kind, root_path=root_path, _loaded_from=root_path, _secrets_loaded_from=str(DEFAULT_SECRETS_PATH))


def load_runtime_secrets_view() -> KVView:
    values, owners = _load_dir_kv(RUNTIME_SECRETS_DIR)
    source_kind = "secrets.d"
    root_path = str(RUNTIME_SECRETS_DIR)

    if not values:
        values = _read_kv_file(RUNTIME_LEGACY_SECRETS)
        owners = {k: "legacy" for k in values.keys()}
        source_kind = "legacy"
        root_path = str(RUNTIME_LEGACY_SECRETS)

    meta = _load_meta_dir(RUNTIME_CONFMETA_DIR)
    return KVView(values=values, owners=owners, meta=meta, source_kind=source_kind, root_path=root_path, _loaded_from=root_path, _secrets_loaded_from=str(DEFAULT_SECRETS_PATH))


def load_source_config_view() -> KVView:
    values, owners = _load_dir_kv(SOURCE_CONF_DIR)
    source_kind = "conf.d"
    root_path = str(SOURCE_CONF_DIR)

    if not values:
        values = _read_kv_file(SOURCE_LEGACY_CONF)
        owners = {k: "legacy" for k in values.keys()}
        source_kind = "legacy"
        root_path = str(SOURCE_LEGACY_CONF)

    meta = _load_meta_dir(SOURCE_CONFMETA_DIR)
    return KVView(values=values, owners=owners, meta=meta, source_kind=source_kind, root_path=root_path, _loaded_from=root_path, _secrets_loaded_from=str(DEFAULT_SECRETS_PATH))


def load_source_secrets_view() -> KVView:
    values, owners = _load_dir_kv(SOURCE_SECRETS_DIR)
    source_kind = "secrets.d"
    root_path = str(SOURCE_SECRETS_DIR)

    if not values:
        values = _read_kv_file(SOURCE_LEGACY_SECRETS)
        owners = {k: "legacy" for k in values.keys()}
        source_kind = "legacy"
        root_path = str(SOURCE_LEGACY_SECRETS)

    meta = _load_meta_dir(SOURCE_CONFMETA_DIR)
    return KVView(values=values, owners=owners, meta=meta, source_kind=source_kind, root_path=root_path, _loaded_from=root_path, _secrets_loaded_from=str(DEFAULT_SECRETS_PATH))


def _render_component_kv(component: str, kv: dict[str, str]) -> str:
    lines = [f"# component: {component}"]
    for k in sorted(kv.keys()):
        lines.append(f"{k} = {kv.get(k, '')}")
    lines.append("")
    return "\n".join(lines)


def _write_component_file(dir_path: Path, component: str, kv: dict[str, str]) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    dst = dir_path / f"{component}.conf"
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    tmp.write_text(_render_component_kv(component, kv), encoding="utf-8")
    tmp.replace(dst)


def _write_split_dir(dir_path: Path, view: KVView) -> None:
    buckets: dict[str, dict[str, str]] = {}
    for key in sorted(view.values.keys()):
        component = view.component_for(key)
        buckets.setdefault(component, {})
        buckets[component][key] = view.values[key]

    dir_path.mkdir(parents=True, exist_ok=True)
    for old in dir_path.glob("*.conf"):
        old.unlink()

    for component, kv in sorted(buckets.items()):
        _write_component_file(dir_path, component, kv)


def save_runtime_config_view(view: KVView) -> KVView:
    if view.source_kind == "conf.d":
        _write_split_dir(RUNTIME_CONF_DIR, view)
    else:
        RUNTIME_LEGACY_CONF.write_text(
            "\n".join(["[takctl]", "# written by takctl.config_store", ""] + [f"{k} = {view.values[k]}" for k in sorted(view.values.keys())] + [""]),
            encoding="utf-8",
        )
    return load_runtime_config_view()


def save_runtime_secrets_view(view: KVView) -> KVView:
    if view.source_kind == "secrets.d":
        _write_split_dir(RUNTIME_SECRETS_DIR, view)
    else:
        RUNTIME_LEGACY_SECRETS.write_text(
            "\n".join(["[takctl-secrets]", "# written by takctl.config_store", ""] + [f"{k} = {view.values[k]}" for k in sorted(view.values.keys())] + [""]),
            encoding="utf-8",
        )
    return load_runtime_secrets_view()


def apply_runtime_updates(
    *,
    config_updates: dict[str, Any] | None = None,
    secret_updates: dict[str, Any] | None = None,
) -> tuple[KVView, KVView]:
    cfg = load_runtime_config_view()
    sec = load_runtime_secrets_view()

    for name, value in (config_updates or {}).items():
        cfg.set(str(name), value)

    for name, value in (secret_updates or {}).items():
        sec.set(str(name), value)

    cfg2 = save_runtime_config_view(cfg)
    sec2 = save_runtime_secrets_view(sec)
    return cfg2, sec2


def runtime_public_state() -> dict[str, Any]:
    cfg = load_runtime_config_view()
    sec = load_runtime_secrets_view()
    names: set[str] = set(cfg.keys()) | set(sec.keys()) | set(cfg.meta.keys()) | set(sec.meta.keys())
    items: list[dict[str, Any]] = []

    meta_merged = dict(cfg.meta)
    meta_merged.update(sec.meta)

    for name in sorted(names):
        m = dict(meta_merged.get(name, {}))
        is_secret = bool(m.get("secret", False)) or (name in sec.values)
        component = str(m.get("component") or (sec.component_for(name) if is_secret else cfg.component_for(name)))

        if is_secret:
            items.append({
                "name": name,
                "secret": True,
                "is_set": bool(sec.get(name, "")),
                "value": "",
                "component": component,
                "meta": m,
            })
        else:
            items.append({
                "name": name,
                "secret": False,
                "is_set": bool(cfg.get(name, "")),
                "value": cfg.get(name, str(m.get("default", ""))),
                "component": component,
                "meta": m,
            })

    return {
        "items": items,
        "config_source_kind": cfg.source_kind,
        "config_root_path": cfg.root_path,
        "secrets_source_kind": sec.source_kind,
        "secrets_root_path": sec.root_path,
    }
