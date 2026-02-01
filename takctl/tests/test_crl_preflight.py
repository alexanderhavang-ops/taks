from types import SimpleNamespace
from pathlib import Path
import pytest

from takctl.services import crl as crlmod


class FakeDB:
    def __init__(self, scalars=None, fetches=None, fail_connect=False):
        self.scalars = scalars or {}
        self.fetches = fetches or {}
        self.fail_connect = fail_connect

    def scalar(self, sql, params=()):
        if self.fail_connect:
            raise RuntimeError("no connect")
        key = " ".join(sql.split())
        return self.scalars.get(key, "")

    def fetchall(self, sql, params=()):
        if self.fail_connect:
            raise RuntimeError("no connect")
        key = " ".join(sql.split())
        return self.fetches.get(key, [])


def _mk_dummy_helper(tmp_path: Path) -> Path:
    p = tmp_path / "bin" / "takctl-crl-sign"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    p.chmod(0o755)
    return p


def mkctx(tmp_path, *, is_root=True, db=None):
    ca_dir = tmp_path / "00_CA"
    ca_dir.mkdir()
    (ca_dir / "openssl-crl.cnf").write_text("dummy", encoding="utf-8")

    if is_root:
        (ca_dir / "ca.key").write_text("dummy", encoding="utf-8")

    helper = _mk_dummy_helper(tmp_path)

    cfg = SimpleNamespace(
        ca_dir=str(ca_dir),
        crl_path=str(tmp_path / "ca.crl"),
        crl_sign_helper=str(helper),
    )
    ctx = SimpleNamespace(cfg=cfg, db=db or FakeDB())
    return ctx


def test_preflight_missing_openssl(monkeypatch, tmp_path):
    ctx = mkctx(tmp_path, is_root=True)
    monkeypatch.setattr(crlmod, "_which", lambda _: None)

    with pytest.raises(crlmod.CrlError) as e:
        crlmod.rebuild_crl_from_db(ctx)

    assert "openssl not found" in str(e.value)


def test_preflight_db_connect_fail(monkeypatch, tmp_path):
    monkeypatch.setattr(crlmod, "_which", lambda _: "/usr/bin/openssl")
    ctx = mkctx(tmp_path, is_root=True, db=FakeDB(fail_connect=True))

    with pytest.raises(crlmod.CrlError) as e:
        crlmod.rebuild_crl_from_db(ctx)

    assert "DB connection failed" in str(e.value)


def test_preflight_db_schema_missing_table(monkeypatch, tmp_path):
    monkeypatch.setattr(crlmod, "_which", lambda _: "/usr/bin/openssl")
    scalars = {
        "SELECT current_user": "takctl_crl_ro",
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='certificate'": "",
    }
    ctx = mkctx(tmp_path, is_root=True, db=FakeDB(scalars=scalars))

    with pytest.raises(crlmod.CrlError) as e:
        crlmod.rebuild_crl_from_db(ctx)

    assert "public.certificate" in str(e.value)


def test_preflight_db_schema_missing_columns(monkeypatch, tmp_path):
    monkeypatch.setattr(crlmod, "_which", lambda _: "/usr/bin/openssl")
    scalars = {
        "SELECT current_user": "takctl_crl_ro",
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='certificate'": "1",
    }
    fetches = {
        "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='certificate'": [
            ("certificate",),
            # revocation_date missing
        ],
    }
    ctx = mkctx(tmp_path, is_root=True, db=FakeDB(scalars=scalars, fetches=fetches))

    with pytest.raises(crlmod.CrlError) as e:
        crlmod.rebuild_crl_from_db(ctx)

    assert "missing columns" in str(e.value)

