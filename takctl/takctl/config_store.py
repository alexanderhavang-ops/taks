from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RUNTIME_ROOT = Path("/opt/tak/tools/takctl")
RUNTIME_CONF_DIR = RUNTIME_ROOT / "conf.d"
RUNTIME_SECRETS_DIR = RUNTIME_ROOT / "secrets.d"
RUNTIME_CONFMETA_DIR = RUNTIME_ROOT / "confmeta"

DEFAULT_CONFIG_PATH = str(RUNTIME_CONF_DIR)
DEFAULT_SECRETS_PATH = str(RUNTIME_SECRETS_DIR)

SOURCE_ROOT = Path("/opt/taks/takctl")
SOURCE_CONF_DIR = SOURCE_ROOT / "conf.d"
SOURCE_SECRETS_DIR = SOURCE_ROOT / "secrets.d"
SOURCE_CONFMETA_DIR = SOURCE_ROOT / "confmeta"


def _fail(msg: str) -> RuntimeError:
    return RuntimeError(f"takctl config error: {msg}")


def _parse_kv_text(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in str(text or "").splitlines():
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


def _component_name(path: Path) -> str:
    name = path.name
    if name.endswith(".conf.template"):
        return name[: -len(".template")]
    if name.endswith(".conf"):
        return name[: -len(".conf")]
    return path.stem


def _load_dir_kv(dir_path: Path, *, allow_templates: bool) -> tuple[dict[str, str], dict[str, str]]:
    if not dir_path.exists():
        raise _fail(f"required directory missing: {dir_path}")
    if not dir_path.is_dir():
        raise _fail(f"required path is not a directory: {dir_path}")

    patterns = ["*.conf"]
    if allow_templates:
        patterns.append("*.conf.template")

    files: list[Path] = []
    seen: set[Path] = set()
    for pat in patterns:
        for p in sorted(dir_path.glob(pat)):
            if p.is_file() and p not in seen:
                files.append(p)
                seen.add(p)

    if not files:
        raise _fail(f"no config fragments found in: {dir_path}")

    merged: dict[str, str] = {}
    owners: dict[str, str] = {}
    for p in files:
        kv = _parse_kv_text(p.read_text(encoding="utf-8"))
        component = _component_name(p)
        for k, v in kv.items():
            merged[k] = v
            owners[k] = component

    if not merged:
        raise _fail(f"no key/value settings found in: {dir_path}")

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
            row = dict(meta)
            row.setdefault("name", str(name))
            row.setdefault("component", component)
            merged[str(name)] = row

    return merged


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


def _write_split_dir(dir_path: Path, view: "KVView") -> None:
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

    def require(self, key: str) -> str:
        k = str(key)
        v = self.values.get(k)
        if v is None or str(v).strip() == "":
            raise _fail(f"missing required key: {k}")
        return str(v)

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
    values, owners = _load_dir_kv(RUNTIME_CONF_DIR, allow_templates=False)
    meta = _load_meta_dir(RUNTIME_CONFMETA_DIR)
    return KVView(
        values=values,
        owners=owners,
        meta=meta,
        source_kind="conf.d",
        root_path=str(RUNTIME_CONF_DIR),
        _loaded_from=str(RUNTIME_CONF_DIR),
        _secrets_loaded_from=str(RUNTIME_SECRETS_DIR),
    )


def load_runtime_secrets_view() -> KVView:
    values, owners = _load_dir_kv(RUNTIME_SECRETS_DIR, allow_templates=False)
    meta = _load_meta_dir(RUNTIME_CONFMETA_DIR)
    return KVView(
        values=values,
        owners=owners,
        meta=meta,
        source_kind="secrets.d",
        root_path=str(RUNTIME_SECRETS_DIR),
        _loaded_from=str(RUNTIME_SECRETS_DIR),
        _secrets_loaded_from=str(RUNTIME_SECRETS_DIR),
    )


def load_source_config_view() -> KVView:
    values, owners = _load_dir_kv(SOURCE_CONF_DIR, allow_templates=True)
    meta = _load_meta_dir(SOURCE_CONFMETA_DIR)
    return KVView(
        values=values,
        owners=owners,
        meta=meta,
        source_kind="conf.d",
        root_path=str(SOURCE_CONF_DIR),
        _loaded_from=str(SOURCE_CONF_DIR),
        _secrets_loaded_from=str(SOURCE_SECRETS_DIR),
    )


def load_source_secrets_view() -> KVView:
    values, owners = _load_dir_kv(SOURCE_SECRETS_DIR, allow_templates=True)
    meta = _load_meta_dir(SOURCE_CONFMETA_DIR)
    return KVView(
        values=values,
        owners=owners,
        meta=meta,
        source_kind="secrets.d",
        root_path=str(SOURCE_SECRETS_DIR),
        _loaded_from=str(SOURCE_SECRETS_DIR),
        _secrets_loaded_from=str(SOURCE_SECRETS_DIR),
    )


def save_runtime_config_view(view: KVView) -> KVView:
    _write_split_dir(RUNTIME_CONF_DIR, view)
    return load_runtime_config_view()


def save_runtime_secrets_view(view: KVView) -> KVView:
    _write_split_dir(RUNTIME_SECRETS_DIR, view)
    return load_runtime_secrets_view()


def apply_runtime_updates(
    *,
    config_updates: dict[str, Any] | None = None,
    secret_updates: dict[str, Any] | None = None,
) -> tuple[KVView, KVView]:
    cfg = load_runtime_config_view()
    sec = load_runtime_secrets_view()

    for k, v in (config_updates or {}).items():
        cfg.set(str(k), v)

    for k, v in (secret_updates or {}).items():
        sec.set(str(k), v)

    cfg = save_runtime_config_view(cfg)
    sec = save_runtime_secrets_view(sec)
    return cfg, sec


def runtime_public_state() -> dict[str, Any]:
    cfg = load_runtime_config_view()
    sec = load_runtime_secrets_view()
    return {
        "config_path": str(RUNTIME_CONF_DIR),
        "secrets_path": str(RUNTIME_SECRETS_DIR),
        "config_source_kind": cfg.source_kind,
        "secrets_source_kind": sec.source_kind,
        "config": dict(cfg.values),
        "secrets": dict(sec.values),
        "meta": dict(cfg.meta),
    }
