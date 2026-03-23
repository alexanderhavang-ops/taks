from __future__ import annotations

import socket
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Optional


RUNTIME_CONFIG_PATH = "/opt/tak/tools/takctl/takctl.conf"
RUNTIME_SECRETS_PATH = "/opt/tak/tools/takctl/secrets.conf"

DEFAULT_CONFIG_PATH = RUNTIME_CONFIG_PATH
DEFAULT_SECRETS_PATH = RUNTIME_SECRETS_PATH


def _parse_conf_kv(path: str) -> dict[str, str]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)

    out: dict[str, str] = {}
    for raw in p.read_text(encoding="utf-8").splitlines():
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


def _to_bool(name: str, value: str) -> bool:
    v = str(value).strip().lower()
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off"):
        return False
    raise ValueError(f"invalid boolean for {name}: {value!r}")


def _to_int(name: str, value: str) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        raise ValueError(f"invalid int for {name}: {value!r}")


def _to_float(name: str, value: str) -> float:
    try:
        return float(str(value).strip())
    except Exception:
        raise ValueError(f"invalid float for {name}: {value!r}")


def _bool_str(v: bool) -> str:
    return "true" if bool(v) else "false"


def _ensure_parent_dir(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


@dataclass
class Secrets:
    db_password: str
    ca_signing_p12_pass: str
    bedrock_api_key: str
    _loaded_from: Optional[str] = None

    def validate(self) -> None:
        return


@dataclass
class Config:
    # DB
    db_mode: str
    db_name: str
    db_host: str
    db_port: int
    db_user: str
    sudo_user: str

    # Identity
    battalion: str
    fqdn: str
    hostname: str

    # Paths
    coreconfig_path: str
    ca_dir: str
    crl_path: str

    # CRL signing helper + CA signing keystore
    crl_sign_helper: str
    crl_sign_helper_timeout_sec: int
    ca_signing_p12: str
    ca_signing_alias: str

    # CRL
    crl_days: int

    tak_service: str

    # LLM
    llm_enabled: bool
    llm_provider: str
    llm_url: str
    llm_model: str
    llm_timeout_s: int
    llm_n_predict: int
    llm_temperature: float
    llm_phase2_evidence_profile: str
    llm_phase3_mode: str
    llm_infra_dir: str
    llm_state_dir: str
    aws_region: str
    bedrock_model_id: str

    # Onboarding
    onboarding_card_ttl_sec: int
    onboarding_print_card_ttl_sec: int
    onboarding_import_card_ttl_sec: int
    onboarding_from_addr: str
    onboarding_external_base: str
    onboarding_import_tmp: str

    # Policy
    default_policy_id: str
    policy_dir: str

    # Logging
    audit_log: str

    # Martine
    martine_state_dir: str
    martine_log_level: str
    martine_mcp_bind_host: str
    martine_mcp_bind_port: int
    martine_cot_udp_host: str
    martine_cot_udp_port: int
    martine_cot_listen_host: str
    martine_cot_listen_port: int
    martine_callsign: str

    # Internal/debug
    _loaded_from: str
    _secrets_loaded_from: Optional[str] = None

    def validate(self) -> None:
        if self.db_mode not in ("psql_sudo", "psycopg2"):
            raise ValueError(f"invalid db_mode={self.db_mode!r}")

        for label, p in (
            ("coreconfig_path", self.coreconfig_path),
            ("ca_dir", self.ca_dir),
            ("ca_signing_p12", self.ca_signing_p12),
            ("crl_sign_helper", self.crl_sign_helper),
        ):
            if not p:
                raise ValueError(f"{label} is empty")
            if not Path(p).exists():
                raise FileNotFoundError(f"{label} does not exist: {p}")

        crl_parent = Path(self.crl_path).parent
        if not crl_parent.exists():
            raise FileNotFoundError(f"crl_path parent directory does not exist: {crl_parent}")

        for label, v in (
            ("onboarding_card_ttl_sec", self.onboarding_card_ttl_sec),
            ("onboarding_print_card_ttl_sec", self.onboarding_print_card_ttl_sec),
            ("onboarding_import_card_ttl_sec", self.onboarding_import_card_ttl_sec),
        ):
            if int(v) < 60:
                raise ValueError(f"{label} must be >= 60")

        if self.llm_provider not in ("local", "bedrock"):
            raise ValueError(f"invalid llm_provider={self.llm_provider!r}")

        if self.llm_phase2_evidence_profile not in ("compact", "full"):
            raise ValueError(
                f"invalid llm_phase2_evidence_profile={self.llm_phase2_evidence_profile!r}"
            )

        if self.llm_phase3_mode not in ("llm", "fallback"):
            raise ValueError(f"invalid llm_phase3_mode={self.llm_phase3_mode!r}")

        sec = load_secrets(self._secrets_loaded_from or DEFAULT_SECRETS_PATH)

        if self.db_mode == "psycopg2":
            if not sec.db_password:
                raise ValueError("db_mode=psycopg2 requires db_password in secrets.conf")

        if self.llm_provider == "bedrock":
            if not self.aws_region:
                raise ValueError("llm_provider=bedrock requires aws_region in takctl.conf")
            if not self.bedrock_model_id:
                raise ValueError("llm_provider=bedrock requires bedrock_model_id in takctl.conf")
            if not sec.bedrock_api_key:
                raise ValueError("llm_provider=bedrock requires bedrock_api_key in secrets.conf")


def load_secrets(path: Optional[str] = None) -> Secrets:
    sec_path = path or DEFAULT_SECRETS_PATH
    p = Path(sec_path)

    if not p.exists():
        sec = Secrets(
            db_password="",
            ca_signing_p12_pass="",
            bedrock_api_key="",
            _loaded_from=None,
        )
        sec.validate()
        return sec

    kv = _parse_conf_kv(sec_path)

    sec = Secrets(
        db_password=(kv.get("db_password") or "").strip(),
        ca_signing_p12_pass=(kv.get("ca_signing_p12_pass") or "").strip(),
        bedrock_api_key=(kv.get("bedrock_api_key") or "").strip(),
        _loaded_from=sec_path,
    )
    sec.validate()
    return sec


def load_config(path: Optional[str] = None, *, secrets_path: Optional[str] = None) -> Config:
    conf_path = path or DEFAULT_CONFIG_PATH
    file_kv = _parse_conf_kv(conf_path)
    sec_path = secrets_path or DEFAULT_SECRETS_PATH

    def opt(name: str, default: str) -> str:
        v = file_kv.get(name)
        if v is None or v == "":
            return default
        return v

    cfg = Config(
        battalion=opt("battalion", ""),
        fqdn=opt("fqdn", ""),
        hostname=opt("hostname", socket.gethostname()),

        db_mode=opt("db_mode", "psql_sudo"),
        db_name=opt("db_name", "cot"),
        db_host=opt("db_host", "127.0.0.1"),
        db_port=_to_int("db_port", opt("db_port", "5432")),
        db_user=opt("db_user", "postgres"),
        sudo_user=opt("sudo_user", "postgres"),

        coreconfig_path=opt("coreconfig_path", "/opt/tak/CoreConfig.xml"),
        ca_dir=opt("ca_dir", "/opt/tak/certs/files/00_CA"),
        crl_path=opt("crl_path", "/opt/tak/certs/files/ca.crl"),

        crl_sign_helper=opt("crl_sign_helper", "/opt/tak/tools/takctl/bin/takctl-crl-sign"),
        crl_sign_helper_timeout_sec=_to_int(
            "crl_sign_helper_timeout_sec",
            opt("crl_sign_helper_timeout_sec", "60"),
        ),
        ca_signing_p12=opt("ca_signing_p12", "/opt/tak/certs/files/00_CA/ca-signing.p12"),
        ca_signing_alias=opt("ca_signing_alias", "tak-ca"),

        crl_days=_to_int("crl_days", opt("crl_days", "30")),
        tak_service=opt("tak_service", "takserver"),

        llm_enabled=_to_bool("llm_enabled", opt("llm_enabled", "true")),
        llm_provider=opt("llm_provider", "local"),
        llm_url=opt("llm_url", "http://127.0.0.1:8090/v1/completions"),
        llm_model=opt("llm_model", "local-small"),
        llm_timeout_s=_to_int("llm_timeout_s", opt("llm_timeout_s", "900")),
        llm_n_predict=_to_int("llm_n_predict", opt("llm_n_predict", "700")),
        llm_temperature=_to_float("llm_temperature", opt("llm_temperature", "0.2")),
        llm_phase2_evidence_profile=opt("llm_phase2_evidence_profile", "compact"),
        llm_phase3_mode=opt("llm_phase3_mode", "fallback"),
        llm_infra_dir=opt("llm_infra_dir", "/opt/tak/tools/takctl/llm-infra"),
        llm_state_dir=opt("llm_state_dir", "/opt/tak/tools/takctl/state"),
        aws_region=opt("aws_region", ""),
        bedrock_model_id=opt("bedrock_model_id", ""),

        onboarding_card_ttl_sec=_to_int(
            "onboarding_card_ttl_sec",
            opt("onboarding_card_ttl_sec", "600"),
        ),
        onboarding_print_card_ttl_sec=_to_int(
            "onboarding_print_card_ttl_sec",
            opt("onboarding_print_card_ttl_sec", "86400"),
        ),
        onboarding_import_card_ttl_sec=_to_int(
            "onboarding_import_card_ttl_sec",
            opt("onboarding_import_card_ttl_sec", "3600"),
        ),
        onboarding_from_addr=opt("onboarding_from_addr", "taks-onboarding@localhost"),
        onboarding_external_base=opt("onboarding_external_base", ""),
        onboarding_import_tmp=opt("onboarding_import_tmp", "/tmp"),

        default_policy_id=opt("default_policy_id", "hemvarnet"),
        policy_dir=opt("policy_dir", ""),

        audit_log=opt("audit_log", "/opt/tak/tools/takctl/takctl.audit.log"),

        martine_state_dir=opt("martine_state_dir", "/opt/tak/tools/martine/state"),
        martine_log_level=opt("martine_log_level", "INFO"),
        martine_mcp_bind_host=opt("martine_mcp_bind_host", "127.0.0.1"),
        martine_mcp_bind_port=_to_int("martine_mcp_bind_port", opt("martine_mcp_bind_port", "8765")),
        martine_cot_udp_host=opt("martine_cot_udp_host", "127.0.0.1"),
        martine_cot_udp_port=_to_int("martine_cot_udp_port", opt("martine_cot_udp_port", "6969")),
        martine_cot_listen_host=opt("martine_cot_listen_host", "0.0.0.0"),
        martine_cot_listen_port=_to_int("martine_cot_listen_port", opt("martine_cot_listen_port", "6970")),
        martine_callsign=opt("martine_callsign", "Martine"),

        _loaded_from=conf_path,
        _secrets_loaded_from=sec_path,
    )

    cfg.validate()
    return cfg


def render_config(cfg: Config) -> str:
    lines = [
        "[takctl]",
        "# written by takctl.config",
        "",
        f"db_mode = {cfg.db_mode}",
        f"db_name = {cfg.db_name}",
        f"db_host = {cfg.db_host}",
        f"db_port = {cfg.db_port}",
        f"db_user = {cfg.db_user}",
        f"sudo_user = {cfg.sudo_user}",
        "",
        f"battalion = {cfg.battalion}",
        f"fqdn = {cfg.fqdn}",
        f"hostname = {cfg.hostname}",
        "",
        f"coreconfig_path = {cfg.coreconfig_path}",
        f"ca_dir = {cfg.ca_dir}",
        f"crl_path = {cfg.crl_path}",
        "",
        f"crl_sign_helper = {cfg.crl_sign_helper}",
        f"crl_sign_helper_timeout_sec = {cfg.crl_sign_helper_timeout_sec}",
        f"ca_signing_p12 = {cfg.ca_signing_p12}",
        f"ca_signing_alias = {cfg.ca_signing_alias}",
        "",
        f"crl_days = {cfg.crl_days}",
        f"tak_service = {cfg.tak_service}",
        "",
        f"llm_enabled = {_bool_str(cfg.llm_enabled)}",
        f"llm_provider = {cfg.llm_provider}",
        f"llm_url = {cfg.llm_url}",
        f"llm_model = {cfg.llm_model}",
        f"llm_timeout_s = {cfg.llm_timeout_s}",
        f"llm_n_predict = {cfg.llm_n_predict}",
        f"llm_temperature = {cfg.llm_temperature}",
        f"llm_phase2_evidence_profile = {cfg.llm_phase2_evidence_profile}",
        f"llm_phase3_mode = {cfg.llm_phase3_mode}",
        f"llm_infra_dir = {cfg.llm_infra_dir}",
        f"llm_state_dir = {cfg.llm_state_dir}",
        f"aws_region = {cfg.aws_region}",
        f"bedrock_model_id = {cfg.bedrock_model_id}",
        "",
        f"onboarding_card_ttl_sec = {cfg.onboarding_card_ttl_sec}",
        f"onboarding_print_card_ttl_sec = {cfg.onboarding_print_card_ttl_sec}",
        f"onboarding_import_card_ttl_sec = {cfg.onboarding_import_card_ttl_sec}",
        f"onboarding_from_addr = {cfg.onboarding_from_addr}",
        f"onboarding_external_base = {cfg.onboarding_external_base}",
        f"onboarding_import_tmp = {cfg.onboarding_import_tmp}",
        "",
        f"default_policy_id = {cfg.default_policy_id}",
        f"policy_dir = {cfg.policy_dir}",
        "",
        f"audit_log = {cfg.audit_log}",
        "",
        f"martine_state_dir = {cfg.martine_state_dir}",
        f"martine_log_level = {cfg.martine_log_level}",
        f"martine_mcp_bind_host = {cfg.martine_mcp_bind_host}",
        f"martine_mcp_bind_port = {cfg.martine_mcp_bind_port}",
        f"martine_cot_udp_host = {cfg.martine_cot_udp_host}",
        f"martine_cot_udp_port = {cfg.martine_cot_udp_port}",
        f"martine_cot_listen_host = {cfg.martine_cot_listen_host}",
        f"martine_cot_listen_port = {cfg.martine_cot_listen_port}",
        f"martine_callsign = {cfg.martine_callsign}",
        "",
    ]
    return "\n".join(lines)


def render_secrets(sec: Secrets) -> str:
    lines = [
        "[takctl]",
        "# written by takctl.config",
        "",
        f"db_password = {sec.db_password}",
        f"ca_signing_p12_pass = {sec.ca_signing_p12_pass}",
        f"bedrock_api_key = {sec.bedrock_api_key}",
        "",
    ]
    return "\n".join(lines)


def write_config(cfg: Config, path: Optional[str] = None) -> Config:
    dst = path or DEFAULT_CONFIG_PATH
    cfg._loaded_from = dst
    _ensure_parent_dir(dst)
    Path(dst).write_text(render_config(cfg), encoding="utf-8")
    return load_config(dst, secrets_path=cfg._secrets_loaded_from)


def write_secrets(sec: Secrets, path: Optional[str] = None) -> Secrets:
    dst = path or DEFAULT_SECRETS_PATH
    sec._loaded_from = dst
    _ensure_parent_dir(dst)
    Path(dst).write_text(render_secrets(sec), encoding="utf-8")
    return load_secrets(dst)


_CONFIG_VALUE_TYPES: dict[str, str] = {
    "db_mode": "str",
    "db_name": "str",
    "db_host": "str",
    "db_port": "int",
    "db_user": "str",
    "sudo_user": "str",
    "battalion": "str",
    "fqdn": "str",
    "hostname": "str",
    "coreconfig_path": "str",
    "ca_dir": "str",
    "crl_path": "str",
    "crl_sign_helper": "str",
    "crl_sign_helper_timeout_sec": "int",
    "ca_signing_p12": "str",
    "ca_signing_alias": "str",
    "crl_days": "int",
    "tak_service": "str",
    "llm_enabled": "bool",
    "llm_provider": "str",
    "llm_url": "str",
    "llm_model": "str",
    "llm_timeout_s": "int",
    "llm_n_predict": "int",
    "llm_temperature": "float",
    "llm_phase2_evidence_profile": "str",
    "llm_phase3_mode": "str",
    "llm_infra_dir": "str",
    "llm_state_dir": "str",
    "aws_region": "str",
    "bedrock_model_id": "str",
    "onboarding_card_ttl_sec": "int",
    "onboarding_print_card_ttl_sec": "int",
    "onboarding_import_card_ttl_sec": "int",
    "onboarding_from_addr": "str",
    "onboarding_external_base": "str",
    "onboarding_import_tmp": "str",
    "default_policy_id": "str",
    "policy_dir": "str",
    "audit_log": "str",
    "martine_state_dir": "str",
    "martine_log_level": "str",
    "martine_mcp_bind_host": "str",
    "martine_mcp_bind_port": "int",
}

_SECRET_VALUE_TYPES: dict[str, str] = {
    "db_password": "str",
    "ca_signing_p12_pass": "str",
    "bedrock_api_key": "str",
}


def _coerce_by_type(name: str, value: Any, kind: str) -> Any:
    if kind == "str":
        return "" if value is None else str(value)
    if kind == "bool":
        if isinstance(value, bool):
            return value
        return _to_bool(name, str(value))
    if kind == "int":
        return _to_int(name, str(value))
    if kind == "float":
        return _to_float(name, str(value))
    raise ValueError(f"unsupported type coercion for {name}: {kind}")


def apply_config_updates(
    *,
    config_updates: dict[str, Any] | None = None,
    secret_updates: dict[str, Any] | None = None,
    config_path: Optional[str] = None,
    secrets_path: Optional[str] = None,
) -> tuple[Config, Secrets]:
    cfg = load_config(config_path, secrets_path=secrets_path)
    sec = load_secrets(secrets_path)

    cfg_changes: dict[str, Any] = {}
    sec_changes: dict[str, Any] = {}

    for name, value in (config_updates or {}).items():
        if name not in _CONFIG_VALUE_TYPES:
            raise ValueError(f"unknown config field: {name}")
        cfg_changes[name] = _coerce_by_type(name, value, _CONFIG_VALUE_TYPES[name])

    for name, value in (secret_updates or {}).items():
        if name not in _SECRET_VALUE_TYPES:
            raise ValueError(f"unknown secret field: {name}")
        sec_changes[name] = _coerce_by_type(name, value, _SECRET_VALUE_TYPES[name])

    new_sec = replace(sec, **sec_changes)
    new_sec._loaded_from = sec._loaded_from or (secrets_path or DEFAULT_SECRETS_PATH)

    new_cfg = replace(cfg, **cfg_changes)
    new_cfg._loaded_from = cfg._loaded_from or (config_path or DEFAULT_CONFIG_PATH)
    new_cfg._secrets_loaded_from = new_sec._loaded_from

    new_sec.validate()
    new_cfg.validate()

    saved_sec = write_secrets(new_sec, new_sec._loaded_from)
    new_cfg._secrets_loaded_from = saved_sec._loaded_from
    saved_cfg = write_config(new_cfg, new_cfg._loaded_from)
    return saved_cfg, saved_sec


def config_public_state() -> dict[str, Any]:
    cfg = load_config()
    sec = load_secrets()

    cfg_dict = asdict(cfg)
    sec_dict = asdict(sec)

    cfg_dict.pop("_loaded_from", None)
    cfg_dict.pop("_secrets_loaded_from", None)
    sec_dict.pop("_loaded_from", None)

    items: list[dict[str, Any]] = []

    for name, value in cfg_dict.items():
        items.append({
            "name": name,
            "value": value,
            "secret": False,
            "source": "config",
        })

    for name, value in sec_dict.items():
        items.append({
            "name": name,
            "value": "",
            "secret": True,
            "is_set": bool(str(value or "").strip()),
            "source": "secrets",
        })

    items.sort(key=lambda x: str(x.get("name") or "").lower())

    return {
        "ok": True,
        "config_path": cfg._loaded_from,
        "secrets_path": sec._loaded_from,
        "items": items,
    }
