from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib  # py311+
except ModuleNotFoundError:  # py310
    import tomli as tomllib


DEFAULT_CONFIG_PATH = Path("/etc/taks/tak_orch.conf")
DEFAULT_SECRETS_PATH = Path("/etc/taks/secrets.conf")


class ConfigError(RuntimeError):
    pass


class ConfigValidationError(ConfigError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("invalid configuration")
        self.errors = errors


@dataclass(frozen=True)
class IdentityConfig:
    orchestrator_fqdn: str
    public_base_url: str
    unit_bundle_base_url: str


@dataclass(frozen=True)
class PathsConfig:
    state_dir: str
    artifacts_dir: str
    rendered_bundles_dir: str


@dataclass(frozen=True)
class AwsConfig:
    region: str
    default_ami: str
    default_subnet_id: str
    default_security_group_id: str
    default_instance_profile: str
    default_instance_type: str
    ssh_key_name: str
    route53_zone_id: str
    launch_enabled: bool


@dataclass(frozen=True)
class LetsEncryptConfig:
    mode: str
    email: str
    wildcard_zone: str
    artifact_cert_dir: str


@dataclass(frozen=True)
class BundlesConfig:
    source_repo_root: str
    default_bundle_kind: str
    include_taks_source: bool


@dataclass(frozen=True)
class NodesConfig:
    default_node_domain: str
    default_cert_model: str


@dataclass(frozen=True)
class OrchConfig:
    identity: IdentityConfig
    paths: PathsConfig
    aws: AwsConfig
    letsencrypt: LetsEncryptConfig
    bundles: BundlesConfig
    nodes: NodesConfig


@dataclass(frozen=True)
class AuthSecrets:
    session_secret: str
    operator_user: str
    operator_password: str
    node_api_user: str
    node_api_password: str


@dataclass(frozen=True)
class CloudflareSecrets:
    api_token: str = ""


@dataclass(frozen=True)
class SecretsConfig:
    auth: AuthSecrets
    cloudflare: CloudflareSecrets


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"missing config file: {path}")
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigError(f"invalid TOML root object in: {path}")
    return raw


def _require_section(raw: dict[str, Any], name: str, errors: list[str]) -> dict[str, Any]:
    value = raw.get(name)
    if not isinstance(value, dict):
        errors.append(f"missing section: {name}")
        return {}
    return value


def _require_str(section: dict[str, Any], key: str, path: str, errors: list[str]) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}.{key} is required")
        return ""
    return value.strip()


def _require_bool(section: dict[str, Any], key: str, path: str, errors: list[str]) -> bool:
    value = section.get(key)
    if not isinstance(value, bool):
        errors.append(f"{path}.{key} must be boolean")
        return False
    return value


def parse_orch_config_dict(raw: dict[str, Any]) -> OrchConfig:
    errors: list[str] = []

    identity = _require_section(raw, "identity", errors)
    paths = _require_section(raw, "paths", errors)
    aws = _require_section(raw, "aws", errors)
    letsencrypt = _require_section(raw, "letsencrypt", errors)
    bundles = _require_section(raw, "bundles", errors)
    nodes = _require_section(raw, "nodes", errors)

    out = OrchConfig(
        identity=IdentityConfig(
            orchestrator_fqdn=_require_str(identity, "orchestrator_fqdn", "identity", errors),
            public_base_url=_require_str(identity, "public_base_url", "identity", errors),
            unit_bundle_base_url=_require_str(identity, "unit_bundle_base_url", "identity", errors),
        ),
        paths=PathsConfig(
            state_dir=_require_str(paths, "state_dir", "paths", errors),
            artifacts_dir=_require_str(paths, "artifacts_dir", "paths", errors),
            rendered_bundles_dir=_require_str(paths, "rendered_bundles_dir", "paths", errors),
        ),
        aws=AwsConfig(
            region=_require_str(aws, "region", "aws", errors),
            default_ami=_require_str(aws, "default_ami", "aws", errors),
            default_subnet_id=_require_str(aws, "default_subnet_id", "aws", errors),
            default_security_group_id=_require_str(aws, "default_security_group_id", "aws", errors),
            default_instance_profile=_require_str(aws, "default_instance_profile", "aws", errors),
            default_instance_type=_require_str(aws, "default_instance_type", "aws", errors),
            ssh_key_name=_require_str(aws, "ssh_key_name", "aws", errors),
            route53_zone_id=_require_str(aws, "route53_zone_id", "aws", errors),
            launch_enabled=_require_bool(aws, "launch_enabled", "aws", errors),
        ),
        letsencrypt=LetsEncryptConfig(
            mode=_require_str(letsencrypt, "mode", "letsencrypt", errors),
            email=_require_str(letsencrypt, "email", "letsencrypt", errors),
            wildcard_zone=_require_str(letsencrypt, "wildcard_zone", "letsencrypt", errors),
            artifact_cert_dir=_require_str(letsencrypt, "artifact_cert_dir", "letsencrypt", errors),
        ),
        bundles=BundlesConfig(
            source_repo_root=_require_str(bundles, "source_repo_root", "bundles", errors),
            default_bundle_kind=_require_str(bundles, "default_bundle_kind", "bundles", errors),
            include_taks_source=_require_bool(bundles, "include_taks_source", "bundles", errors),
        ),
        nodes=NodesConfig(
            default_node_domain=_require_str(nodes, "default_node_domain", "nodes", errors),
            default_cert_model=_require_str(nodes, "default_cert_model", "nodes", errors),
        ),
    )

    if errors:
        raise ConfigValidationError(errors)
    return out


def parse_secrets_dict(raw: dict[str, Any]) -> SecretsConfig:
    errors: list[str] = []

    auth = _require_section(raw, "auth", errors)
    cloudflare = raw.get("cloudflare")
    if not isinstance(cloudflare, dict):
        cloudflare = {}

    api_token = cloudflare.get("api_token", "")
    if api_token is None:
        api_token = ""
    if not isinstance(api_token, str):
        errors.append("cloudflare.api_token must be string if present")
        api_token = ""
    api_token = api_token.strip()

    out = SecretsConfig(
        auth=AuthSecrets(
            session_secret=_require_str(auth, "session_secret", "auth", errors),
            operator_user=_require_str(auth, "operator_user", "auth", errors),
            operator_password=_require_str(auth, "operator_password", "auth", errors),
            node_api_user=_require_str(auth, "node_api_user", "auth", errors),
            node_api_password=_require_str(auth, "node_api_password", "auth", errors),
        ),
        cloudflare=CloudflareSecrets(
            api_token=api_token,
        ),
    )

    if errors:
        raise ConfigValidationError(errors)
    return out


def load_orch_config(path: Path = DEFAULT_CONFIG_PATH) -> OrchConfig:
    return parse_orch_config_dict(_read_toml(path))


def load_secrets_config(path: Path = DEFAULT_SECRETS_PATH) -> SecretsConfig:
    return parse_secrets_dict(_read_toml(path))
