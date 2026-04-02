from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


RUNTIME_ROOT = Path("/opt/tak-orch/orchestrator")
CONF_D = RUNTIME_ROOT / "conf.d"
SECRETS_D = RUNTIME_ROOT / "secrets.d"
CONFMETA_D = RUNTIME_ROOT / "confmeta"

LEGACY_CONFIG_PATH = Path("/etc/taks/tak_orch.conf")
LEGACY_SECRETS_PATH = Path("/etc/taks/secrets.conf")


@dataclass
class KVView:
    values: dict[str, str] = field(default_factory=dict)
    root_path: str = str(RUNTIME_ROOT)
    _loaded_from: str = str(RUNTIME_ROOT)

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def set(self, key: str, value: Any, *, component: str | None = None) -> None:
        self.values[str(key)] = "" if value is None else str(value)


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _ensure_runtime_dirs() -> None:
    CONF_D.mkdir(parents=True, exist_ok=True)
    SECRETS_D.mkdir(parents=True, exist_ok=True)
    CONFMETA_D.mkdir(parents=True, exist_ok=True)


def _parse_kv_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _write_kv_file(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for k in sorted(values.keys()):
        lines.append(f"{k} = {values.get(k, '')}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _load_meta() -> dict[str, dict[str, Any]]:
    meta: dict[str, dict[str, Any]] = {}
    if not CONFMETA_D.exists():
        return meta
    for p in sorted(CONFMETA_D.glob("*.json")):
        obj = json.loads(p.read_text(encoding="utf-8"))
        component = str(obj.get("component") or p.stem).strip()
        fields = obj.get("fields") or {}
        if not isinstance(fields, dict):
            continue
        for key, spec in fields.items():
            if not isinstance(spec, dict):
                continue
            entry = {
                "component": component,
                "secret": bool(spec.get("secret", False)),
                "default": "" if spec.get("default") is None else str(spec.get("default")),
                "type": str(spec.get("type") or "string"),
                "doc": str(spec.get("doc") or ""),
                "level": str(spec.get("level") or "basic"),
            }
            if "enum" in spec and isinstance(spec.get("enum"), list):
                entry["enum"] = [str(x) for x in (spec.get("enum") or [])]
            if "min" in spec:
                entry["min"] = spec.get("min")
            if "max" in spec:
                entry["max"] = spec.get("max")
            meta[str(key)] = entry
    return meta


def _legacy_public_values() -> dict[str, str]:
    raw = _read_toml(LEGACY_CONFIG_PATH)
    identity = raw.get("identity") or {}
    paths = raw.get("paths") or {}
    aws = raw.get("aws") or {}
    letsencrypt = raw.get("letsencrypt") or {}
    bundles = raw.get("bundles") or {}
    nodes = raw.get("nodes") or {}

    return {
        "orchestrator_fqdn": str(identity.get("orchestrator_fqdn", "") or ""),
        "public_base_url": str(identity.get("public_base_url", "") or ""),
        "unit_bundle_base_url": str(identity.get("unit_bundle_base_url", "") or ""),

        "state_dir": str(paths.get("state_dir", "") or ""),
        "artifacts_dir": str(paths.get("artifacts_dir", "") or ""),
        "rendered_bundles_dir": str(paths.get("rendered_bundles_dir", "") or ""),

        "aws_region": str(aws.get("region", "") or ""),
        "aws_default_ami": str(aws.get("default_ami", "") or ""),
        "aws_default_vpc_id": str(aws.get("default_vpc_id", "") or ""),
        "aws_default_subnet_id": str(aws.get("default_subnet_id", "") or ""),
        "aws_default_security_group_id": str(aws.get("default_security_group_id", "") or ""),
        "aws_default_instance_profile": str(aws.get("default_instance_profile", "") or ""),
        "aws_default_instance_type": str(aws.get("default_instance_type", "") or ""),
        "aws_default_key_name": str(aws.get("default_key_name", "") or ""),
        "aws_ssh_key_name": str(aws.get("ssh_key_name", "") or ""),
        "aws_route53_zone_id": str(aws.get("route53_zone_id", "") or ""),
        "aws_launch_enabled": "true" if bool(aws.get("launch_enabled", False)) else "false",

        "letsencrypt_mode": str(letsencrypt.get("mode", "") or ""),
        "letsencrypt_email": str(letsencrypt.get("email", "") or ""),
        "letsencrypt_wildcard_zone": str(letsencrypt.get("wildcard_zone", "") or ""),
        "letsencrypt_artifact_cert_dir": str(letsencrypt.get("artifact_cert_dir", "") or ""),

        "bundles_source_repo_root": str(bundles.get("source_repo_root", "") or ""),
        "bundles_default_bundle_kind": str(bundles.get("default_bundle_kind", "") or ""),
        "bundles_include_taks_source": "true" if bool(bundles.get("include_taks_source", False)) else "false",

        "nodes_default_node_domain": str(nodes.get("default_node_domain", "") or ""),
        "nodes_default_cert_model": str(nodes.get("default_cert_model", "") or ""),
    }


def _legacy_secret_values() -> dict[str, str]:
    raw = _read_toml(LEGACY_SECRETS_PATH)
    auth = raw.get("auth") or {}
    return {
        "session_secret": str(auth.get("session_secret", "") or ""),
        "operator_user": str(auth.get("operator_user", "") or ""),
        "operator_password": str(auth.get("operator_password", "") or ""),
        "node_api_user": str(auth.get("node_api_user", "") or ""),
        "node_api_password": str(auth.get("node_api_password", "") or ""),
    }


def _component_file(component: str, *, secret: bool) -> Path:
    base = SECRETS_D if secret else CONF_D
    return base / f"{component}.conf"


def _bootstrap_from_legacy_if_needed() -> None:
    _ensure_runtime_dirs()
    meta = _load_meta()
    if not meta:
        return

    any_runtime = any(CONF_D.glob("*.conf")) or any(SECRETS_D.glob("*.conf"))
    if any_runtime:
        return

    public_vals = _legacy_public_values()
    secret_vals = _legacy_secret_values()

    by_component_public: dict[str, dict[str, str]] = {}
    by_component_secret: dict[str, dict[str, str]] = {}

    for key, spec in meta.items():
        component = str(spec["component"])
        default = str(spec.get("default", "") or "")
        if spec.get("secret", False):
            by_component_secret.setdefault(component, {})[key] = secret_vals.get(key, default)
        else:
            by_component_public.setdefault(component, {})[key] = public_vals.get(key, default)

    for component, values in by_component_public.items():
        _write_kv_file(_component_file(component, secret=False), values)
    for component, values in by_component_secret.items():
        _write_kv_file(_component_file(component, secret=True), values)


def _load_values(*, secret: bool) -> dict[str, str]:
    _bootstrap_from_legacy_if_needed()
    out: dict[str, str] = {}
    base = SECRETS_D if secret else CONF_D
    for p in sorted(base.glob("*.conf")):
        out.update(_parse_kv_file(p))
    meta = _load_meta()
    for key, spec in meta.items():
        if bool(spec.get("secret", False)) == secret and key not in out:
            out[key] = str(spec.get("default", "") or "")
    return out


def load_runtime_config_view() -> KVView:
    return KVView(values=_load_values(secret=False), root_path=str(CONF_D), _loaded_from=str(CONF_D))


def load_runtime_secrets_view() -> KVView:
    return KVView(values=_load_values(secret=True), root_path=str(SECRETS_D), _loaded_from=str(SECRETS_D))


def _save_view(view: KVView, *, secret: bool) -> KVView:
    _ensure_runtime_dirs()
    meta = _load_meta()
    grouped: dict[str, dict[str, str]] = {}
    for key, spec in meta.items():
        if bool(spec.get("secret", False)) != secret:
            continue
        component = str(spec["component"])
        grouped.setdefault(component, {})
        grouped[component][key] = str(view.values.get(key, spec.get("default", "") or ""))

    for component, values in grouped.items():
        _write_kv_file(_component_file(component, secret=secret), values)

    return view


def save_runtime_config_view(cfg: KVView) -> KVView:
    return _save_view(cfg, secret=False)


def save_runtime_secrets_view(sec: KVView) -> KVView:
    return _save_view(sec, secret=True)


def runtime_public_state() -> dict[str, Any]:
    cfg = load_runtime_config_view()
    sec = load_runtime_secrets_view()
    meta = _load_meta()

    public_values = dict(cfg.values)
    secret_keys: list[str] = []
    components: dict[str, dict[str, Any]] = {}

    for key, spec in meta.items():
        component = str(spec["component"])
        components.setdefault(component, {"component": component, "fields": {}})
        field_payload = {
            "type": spec.get("type", "string"),
            "doc": spec.get("doc", ""),
            "secret": bool(spec.get("secret", False)),
            "default": spec.get("default", ""),
            "value": "" if spec.get("secret", False) else public_values.get(key, ""),
            "level": spec.get("level", "basic"),
        }
        if "enum" in spec:
            field_payload["enum"] = spec.get("enum") or []
        if "min" in spec:
            field_payload["min"] = spec.get("min")
        if "max" in spec:
            field_payload["max"] = spec.get("max")
        components[component]["fields"][key] = field_payload
        if spec.get("secret", False):
            secret_keys.append(key)

    return {
        "config_root": str(CONF_D),
        "secrets_root": str(SECRETS_D),
        "config_exists": True,
        "secrets_exists": True,
        "config_path": str(CONF_D),
        "secrets_path": str(SECRETS_D),
        "values": public_values,
        "secret_keys": sorted(secret_keys),
        "components": [components[k] for k in sorted(components.keys())],
        "has_secrets": {k: bool(sec.values.get(k, "").strip()) for k in sorted(secret_keys)},
    }


def apply_runtime_updates(
    *,
    config_updates: dict[str, Any] | None = None,
    secret_updates: dict[str, Any] | None = None,
) -> tuple[KVView, KVView]:
    cfg = load_runtime_config_view()
    sec = load_runtime_secrets_view()

    for k, v in (config_updates or {}).items():
        cfg.set(k, "" if v is None else v)
    for k, v in (secret_updates or {}).items():
        sec.set(k, "" if v is None else v)

    save_runtime_config_view(cfg)
    save_runtime_secrets_view(sec)
    return cfg, sec
