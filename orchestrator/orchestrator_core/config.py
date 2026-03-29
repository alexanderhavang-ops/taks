from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from orchestrator_core.config_store import (
    KVView,
    apply_runtime_updates,
    load_runtime_config_view,
    load_runtime_secrets_view,
    runtime_public_state,
    save_runtime_config_view,
    save_runtime_secrets_view,
)

RuntimeConfig = KVView
RuntimeSecrets = KVView


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
class SecretsConfig:
    auth: AuthSecrets


def _s(v: Any, default: str = "") -> str:
    if v is None:
        return default
    return str(v).strip()


def _b(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    s = _s(v, "").lower()
    if not s:
        return default
    return s in {"1", "true", "yes", "on"}


def load_config(path: Optional[str] = None, *, secrets_path: Optional[str] = None) -> RuntimeConfig:
    return load_runtime_config_view()


def load_secrets(path: Optional[str] = None) -> RuntimeSecrets:
    return load_runtime_secrets_view()


def write_config(cfg: RuntimeConfig, path: Optional[str] = None) -> RuntimeConfig:
    return save_runtime_config_view(cfg)


def write_secrets(sec: RuntimeSecrets, path: Optional[str] = None) -> RuntimeSecrets:
    return save_runtime_secrets_view(sec)


def apply_config_updates(
    *,
    config_updates: dict[str, Any] | None = None,
    secret_updates: dict[str, Any] | None = None,
    config_path: Optional[str] = None,
    secrets_path: Optional[str] = None,
) -> tuple[RuntimeConfig, RuntimeSecrets]:
    return apply_runtime_updates(
        config_updates=config_updates,
        secret_updates=secret_updates,
    )


def config_public_state() -> dict[str, Any]:
    return runtime_public_state()


def load_orch_config() -> OrchConfig:
    cfg = load_runtime_config_view()
    return OrchConfig(
        identity=IdentityConfig(
            orchestrator_fqdn=_s(cfg.get("orchestrator_fqdn")),
            public_base_url=_s(cfg.get("public_base_url")),
            unit_bundle_base_url=_s(cfg.get("unit_bundle_base_url")),
        ),
        paths=PathsConfig(
            state_dir=_s(cfg.get("state_dir")),
            artifacts_dir=_s(cfg.get("artifacts_dir")),
            rendered_bundles_dir=_s(cfg.get("rendered_bundles_dir")),
        ),
        aws=AwsConfig(
            region=_s(cfg.get("aws_region")),
            default_ami=_s(cfg.get("aws_default_ami")),
            default_subnet_id=_s(cfg.get("aws_default_subnet_id")),
            default_security_group_id=_s(cfg.get("aws_default_security_group_id")),
            default_instance_profile=_s(cfg.get("aws_default_instance_profile")),
            default_instance_type=_s(cfg.get("aws_default_instance_type"), "t3.large"),
            ssh_key_name=_s(cfg.get("aws_ssh_key_name")),
            route53_zone_id=_s(cfg.get("aws_route53_zone_id")),
            launch_enabled=_b(cfg.get("aws_launch_enabled"), False),
        ),
        letsencrypt=LetsEncryptConfig(
            mode=_s(cfg.get("le_mode")),
            email=_s(cfg.get("le_email")),
            wildcard_zone=_s(cfg.get("le_wildcard_zone")),
            artifact_cert_dir=_s(cfg.get("le_artifact_cert_dir")),
        ),
        bundles=BundlesConfig(
            source_repo_root=_s(cfg.get("bundles_source_repo_root")),
            default_bundle_kind=_s(cfg.get("bundles_default_bundle_kind")),
            include_taks_source=_b(cfg.get("bundles_include_taks_source"), True),
        ),
        nodes=NodesConfig(
            default_node_domain=_s(cfg.get("nodes_default_node_domain")),
            default_cert_model=_s(cfg.get("nodes_default_cert_model")),
        ),
    )


def load_secrets_config() -> SecretsConfig:
    sec = load_runtime_secrets_view()
    return SecretsConfig(
        auth=AuthSecrets(
            session_secret=_s(sec.get("session_secret")),
            operator_user=_s(sec.get("operator_user")),
            operator_password=_s(sec.get("operator_password")),
            node_api_user=_s(sec.get("node_api_user")),
            node_api_password=_s(sec.get("node_api_password")),
        ),
    )
