from __future__ import annotations

from dataclasses import dataclass

from martine_server.config import load_config as load_server_config
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
    server_cfg = load_server_config()
    takctl_cfg = load_takctl_config()
    return MartineConfig(
        state_dir=server_cfg.state_dir,
        log_level=server_cfg.log_level,
        mcp_bind_host=server_cfg.mcp_bind_host,
        mcp_bind_port=server_cfg.mcp_bind_port,
        cot_udp_host=str(takctl_cfg.get('martine_cot_udp_host', '127.0.0.1')),
        cot_udp_port=int(takctl_cfg.get('martine_cot_udp_port', '6969')),
        cot_listen_host=str(takctl_cfg.get('martine_cot_listen_host', '0.0.0.0')),
        cot_listen_port=int(takctl_cfg.get('martine_cot_listen_port', '6970')),
        callsign=str(takctl_cfg.get('martine_callsign', 'Martine')),
        presence_interval_sec=int(takctl_cfg.get('martine_presence_interval_sec', '30')),
        chat_uid=str(takctl_cfg.get('martine_chat_uid', 'ANDROID-MARTINE')),
        loaded_from=server_cfg.loaded_from,
    )
