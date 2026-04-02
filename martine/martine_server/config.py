from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config_store import load_runtime_config_view, KVView


@dataclass(frozen=True)
class MartineServerConfig:
    state_dir: str
    trace_dir: str
    log_level: str
    mcp_bind_host: str
    mcp_bind_port: int
    default_max_turns: int
    default_max_tool_calls: int
    default_max_output_tokens: int
    default_allow_repair_turn: bool
    loaded_from: str
    raw: KVView


def _truthy(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    s = str(v).strip().lower()
    if s in {'1', 'true', 'yes', 'on'}:
        return True
    if s in {'0', 'false', 'no', 'off'}:
        return False
    return default


def load_config() -> MartineServerConfig:
    cfg = load_runtime_config_view()
    return MartineServerConfig(
        state_dir=str(cfg.get('martine_state_dir', '/opt/tak/tools/martine/state')),
        trace_dir=str(cfg.get('martine_trace_dir', cfg.get('martine_state_dir', '/opt/tak/tools/martine/state') + '/logs')),
        log_level=str(cfg.get('martine_log_level', 'INFO')),
        mcp_bind_host=str(cfg.get('martine_mcp_bind_host', '127.0.0.1')),
        mcp_bind_port=int(cfg.get('martine_mcp_bind_port', '8765')),
        default_max_turns=int(cfg.get('martine_default_max_turns', '6')),
        default_max_tool_calls=int(cfg.get('martine_default_max_tool_calls', '10')),
        default_max_output_tokens=int(cfg.get('martine_default_max_output_tokens', '2000')),
        default_allow_repair_turn=_truthy(cfg.get('martine_default_allow_repair_turn', 'true'), True),
        loaded_from=str(cfg._loaded_from),
        raw=cfg,
    )


def resolve_profile(client: str, workload: str = '', overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = load_config()
    raw = cfg.raw
    keys = []
    client_key = (client or '').strip().replace('-', '_')
    workload_key = (workload or '').strip().replace('-', '_')
    if client_key and workload_key:
        keys.append(f'martine.client.{client_key}.{workload_key}.')
    if client_key:
        keys.append(f'martine.client.{client_key}.')
    resolved = {
        'max_turns': cfg.default_max_turns,
        'max_tool_calls': cfg.default_max_tool_calls,
        'max_output_tokens': cfg.default_max_output_tokens,
        'allow_repair_turn': cfg.default_allow_repair_turn,
    }
    for prefix in keys:
        mt = raw.get(prefix + 'max_turns', '')
        mc = raw.get(prefix + 'max_tool_calls', '')
        mo = raw.get(prefix + 'max_output_tokens', '')
        ar = raw.get(prefix + 'allow_repair_turn', '')
        if mt.strip():
            resolved['max_turns'] = int(mt)
        if mc.strip():
            resolved['max_tool_calls'] = int(mc)
        if mo.strip():
            resolved['max_output_tokens'] = int(mo)
        if ar.strip():
            resolved['allow_repair_turn'] = _truthy(ar, resolved['allow_repair_turn'])
    for k, v in (overrides or {}).items():
        if v is not None:
            resolved[k] = v
    return resolved
