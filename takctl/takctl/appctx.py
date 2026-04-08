from __future__ import annotations

from dataclasses import dataclass

from takctl.config import RuntimeConfig
from takctl.infra.audit import Audit
from takctl.infra.db import DB
from takctl.infra.fs import FS
from takctl.infra.openssl import OpenSSL
from takctl.infra.systemd import Systemd


@dataclass(frozen=True)
class AppContext:
    cfg: RuntimeConfig
    db: DB
    openssl: OpenSSL
    fs: FS
    systemd: Systemd
    audit: Audit


def build_context(cfg: RuntimeConfig) -> AppContext:
    db = DB(cfg)
    openssl = OpenSSL(cfg)
    fs = FS(cfg)
    systemd = Systemd(cfg)
    audit = Audit(cfg)
    return AppContext(cfg=cfg, db=db, openssl=openssl, fs=fs, systemd=systemd, audit=audit)
