from __future__ import annotations

from dataclasses import dataclass

from takctl.config import load_config as load_takctl_config


@dataclass(frozen=True)
class MartineConfig:
    state_dir: str
    log_level: str
    mcp_bind_host: str
    mcp_bind_port: int
    cot_udp_host: str
    cot_udp_port: int
    cot_listen_host: str
    cot_listen_port: int
    callsign: str
    presence_interval_sec: int
    chat_uid: str
    loaded_from: str


def load_config() -> MartineConfig:
    cfg = load_takctl_config()
    return MartineConfig(
        state_dir=str(cfg.get("martine_state_dir", "/opt/tak/tools/martine/state")),
        log_level=str(cfg.get("martine_log_level", "INFO")),
        mcp_bind_host=str(cfg.get("martine_mcp_bind_host", "127.0.0.1")),
        mcp_bind_port=int(cfg.get("martine_mcp_bind_port", "8765")),
        cot_udp_host=str(cfg.get("martine_cot_udp_host", "127.0.0.1")),
        cot_udp_port=int(cfg.get("martine_cot_udp_port", "6969")),
        cot_listen_host=str(cfg.get("martine_cot_listen_host", "0.0.0.0")),
        cot_listen_port=int(cfg.get("martine_cot_listen_port", "6970")),
        callsign=str(cfg.get("martine_callsign", "Martine")),
        presence_interval_sec=int(cfg.get("martine_presence_interval_sec", "30")),
        chat_uid=str(cfg.get("martine_chat_uid", "ANDROID-MARTINE")),
        loaded_from=str(getattr(cfg, "_loaded_from", "")),
    )
