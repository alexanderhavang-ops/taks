from __future__ import annotations

from typing import Any, Optional

from takctl.config_store import (
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


def _render_conf(section: str, values: dict[str, str]) -> str:
    lines = [f"[{section}]", "# written by takctl.config", ""]
    for k in sorted(values.keys()):
        lines.append(f"{k} = {values.get(k, '')}")
    lines.append("")
    return "\n".join(lines)


def load_config(path: Optional[str] = None, *, secrets_path: Optional[str] = None) -> RuntimeConfig:
    return load_runtime_config_view()


def load_secrets(path: Optional[str] = None) -> RuntimeSecrets:
    return load_runtime_secrets_view()


def render_config(cfg: RuntimeConfig) -> str:
    return _render_conf("takctl", cfg.values)


def render_secrets(sec: RuntimeSecrets) -> str:
    return _render_conf("takctl-secrets", sec.values)


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
