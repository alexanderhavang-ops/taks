from __future__ import annotations

import hashlib
import json
import os
import time
import traceback
from pathlib import Path
from typing import Any, List, Tuple

from takctl.services.llm_runs.ops_findings_phase2 import run_phase2_findings
from takctl.services.llm_runs.ops_phase1a import build_ops_brief, write_phase1_artifacts
from takctl.services.llm_runs.snapshot_view import build_snapshot

VIEW = "tactical-operations"

# Curated queries (NO SELECT *; avoid huge fields like groups/bbox/bounding_polygon/etc)
QUERIES: List[Tuple[str, str]] = [
    ("00_tables", """
SELECT table_schema || '.' || table_name AS table_name
FROM information_schema.tables
WHERE table_schema='public'
  AND table_name LIKE 'mission%'
ORDER BY table_name
LIMIT 200
"""),
    ("10_mission_list", """
SELECT
  id,
  guid,
  name,
  creatoruid,
  create_time,
  tool,
  description,
  parent_mission_id,
  default_role_id,
  invite_only,
  expiration,
  last_edited,
  classification
FROM public.mission
ORDER BY create_time DESC NULLS LAST, id DESC
LIMIT 50
"""),
    ("20_subscriptions", """
SELECT
  mission_id,
  client_uid,
  create_time,
  uid,
  role_id,
  username
FROM public.mission_subscription
ORDER BY create_time DESC NULLS LAST, mission_id DESC
LIMIT 200
"""),
    ("30_invitations", """
SELECT
  id,
  mission_id,
  mission_guid,
  mission_name,
  invitee,
  type,
  creator_uid,
  create_time,
  role_id
FROM public.mission_invitation
ORDER BY create_time DESC NULLS LAST, id DESC
LIMIT 200
"""),
    ("40_changes_timeline", """
SELECT
  id,
  mission_id,
  mission_guid,
  mission_name,
  ts,
  change_type,
  creatoruid,
  remote_federated_change,
  servertime
FROM public.mission_change
ORDER BY ts DESC NULLS LAST, id DESC
LIMIT 200
"""),
]

# -----------------------------------------------------------------------------
# Paths / atomic write helpers
# -----------------------------------------------------------------------------

def _state_root() -> Path:
    base = (os.environ.get("TAKCTL_STATE_DIR") or "").strip() or "/opt/tak/tools/takctl/state"
    p = Path(base) / "llm" / VIEW
    p.mkdir(parents=True, exist_ok=True)
    (p / "runs").mkdir(parents=True, exist_ok=True)
    return p

def _utc_run_id(ts: int | None = None) -> str:
    if ts is None:
        ts = int(time.time())
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(ts))

def _utc_iso(ts: int | None = None) -> str:
    if ts is None:
        ts = int(time.time())
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))

def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def _read_self_bytes() -> bytes:
    try:
        return Path(__file__).read_bytes()
    except Exception:
        return b""

def _write_json_atomic(path: Path, obj: Any, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(tmp, mode)
    tmp.replace(path)

def _meta(out_path: Path, run_id: str) -> dict[str, Any]:
    self_bytes = _read_self_bytes()
    return {
        "view": VIEW,
        "run_id": run_id,
        "generated_utc": _utc_iso(),
        "generator_module": __name__,
        "generator_file": str(Path(__file__).resolve()),
        "generator_sha256": _sha256_bytes(self_bytes) if self_bytes else None,
        "out_path": str(out_path),
    }

# -----------------------------------------------------------------------------
# SQL guard (KISS)
# -----------------------------------------------------------------------------

def _clean_sql_for_guard(sql_raw: str) -> str:
    # Drop full-line "--" comments, remove blank lines, drop trailing ';'.
    lines: List[str] = []
    for ln in (sql_raw or "").replace("\ufeff", "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("--"):
            continue
        lines.append(ln)
    sql = "\n".join(lines).strip()
    if sql.endswith(";"):
        sql = sql[:-1].rstrip()
    return sql

def _guard_sql(sql_clean: str) -> tuple[bool, str | None]:
    s = (sql_clean or "").lstrip()
    if not s:
        return False, "empty_sql"
    head = s[:8].lower()
    if not (head.startswith("select") or head.startswith("with")):
        return False, "only SELECT/WITH queries are allowed"
    if ";" in s:
        return False, "only single-statement queries are allowed (no ';')"
    return True, None

# -----------------------------------------------------------------------------
# Redaction (KISS)
# -----------------------------------------------------------------------------

_REDACT_KEYS = {"token", "password", "secret", "api_key", "apikey", "private_key", "key", "cert"}

def _redact_value(k: str, v: Any) -> Any:
    kk = (k or "").lower()
    if kk in _REDACT_KEYS and v not in (None, ""):
        return "***REDACTED***"
    return v

def _redact_row(d: dict[str, Any]) -> dict[str, Any]:
    return {str(k): _redact_value(str(k), v) for k, v in (d or {}).items()}

# -----------------------------------------------------------------------------
# DB env + connection
# -----------------------------------------------------------------------------

def _load_env_file_if_needed() -> None:
    if (os.environ.get("TAKCTL_DB_PASSWORD") or "").strip():
        return
    candidates = [Path("/opt/tak/tools/takctl/secrets/db.env"), Path("/opt/tak/tools/takctl/secrets/db.env.local")]
    for fp in candidates:
        if not fp.exists():
            continue
        try:
            for ln in fp.read_text(encoding="utf-8").splitlines():
                ln = ln.strip()
                if not ln or ln.startswith("#") or "=" not in ln:
                    continue
                k, v = ln.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'").strip('"')
                if k and k not in os.environ:
                    os.environ[k] = v
        except Exception:
            pass
        return

def _db_connect():
    import psycopg2  # type: ignore
    _load_env_file_if_needed()
    host = os.environ.get("TAKCTL_DB_HOST") or "127.0.0.1"
    port = int(os.environ.get("TAKCTL_DB_PORT") or "5432")
    dbname = os.environ.get("TAKCTL_DB_NAME") or "cot"
    user = os.environ.get("TAKCTL_DB_USER") or "tak"
    password = os.environ.get("TAKCTL_DB_PASSWORD") or ""
    return psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)

def _run_query(conn, name: str, sql_raw: str, row_limit: int = 200) -> dict[str, Any]:
    t0 = time.time()
    sql_clean = _clean_sql_for_guard(sql_raw)
    ok_guard, guard_err = _guard_sql(sql_clean)

    out: dict[str, Any] = {
        "name": name,
        "ok": False,
        "elapsed_ms": None,
        "error": None,
        "sql_raw": (sql_raw or "").strip(),
        "sql": sql_clean,
        "sql_sha256": _sha256_bytes(sql_clean.encode("utf-8")),
        "columns": None,
        "row_count": 0,
        "rows": [],
        "truncated": False,
        "preview_len": 0,
    }

    if not ok_guard:
        out["error"] = f"rejected: {guard_err}"
        out["elapsed_ms"] = int((time.time() - t0) * 1000)
        return out

    try:
        with conn.cursor() as cur:
            cur.execute(sql_clean)
            cols = [d[0] for d in (cur.description or [])]
            raw_rows = cur.fetchmany(row_limit + 1)

            truncated = len(raw_rows) > row_limit
            if truncated:
                raw_rows = raw_rows[:row_limit]

            dict_rows: List[dict[str, Any]] = []
            for r in raw_rows:
                d: dict[str, Any] = {}
                for i, c in enumerate(cols):
                    v = r[i]
                    try:
                        json.dumps(v)
                        d[c] = v
                    except Exception:
                        d[c] = str(v)
                dict_rows.append(_redact_row(d))

            out["ok"] = True
            out["columns"] = cols
            out["rows"] = dict_rows
            out["row_count"] = len(dict_rows)
            out["truncated"] = bool(truncated)
            out["preview_len"] = len(dict_rows)

    except Exception as e:
        out["ok"] = False
        out["error"] = f"{type(e).__name__}: {e}"

    out["elapsed_ms"] = int((time.time() - t0) * 1000)
    return out

# -----------------------------------------------------------------------------
# Main generator
# -----------------------------------------------------------------------------

def run_once() -> dict[str, Any]:
    root = _state_root()
    ts = int(time.time())
    run_id = _utc_run_id(ts)

    # Single-flight lock: prevent overlapping runs (timer + manual start, slow LLM, etc.)
    lock_fd = None
    try:
        lock_path = root / ".run.lock"
        lock_fd = lock_path.open("w", encoding="utf-8")
        try:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # Another run is in progress. Exit quickly and deterministically.
            return {
                "_meta": _meta(root / "runs" / f"{run_id}.json", run_id),
                "ok": False,
                "view": VIEW,
                "run_id": run_id,
                "ts_utc": _utc_iso(ts),
                "elapsed_ms": 0,
                "error": "already_running",
                "traceback": None,
                "notes": ["single-flight lock: another run holds .run.lock"],
            }
        lock_fd.write(run_id + "\n")
        lock_fd.flush()
    except Exception:
        # If locking fails for any reason, continue (best-effort; don't brick the generator).
        pass

    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    phase0_path = run_dir / "phase0.json"
    phase0_latest_path = root / "phase0_latest.json"
    snapshot_path = root / "snapshot.json"

    latest_path = root / "latest.json"
    last_run_path = root / "last_run.json"
    run_path = root / "runs" / f"{run_id}.json"

    phase1_latest_path = root / "phase1_latest.json"
    phase2_latest_path = root / "phase2_latest.json"

    t0 = time.time()
    rec: dict[str, Any] = {
        "_meta": _meta(run_path, run_id),
        "ok": False,
        "view": VIEW,
        "run_id": run_id,
        "ts_utc": _utc_iso(ts),
        "elapsed_ms": None,
        "error": None,
        "traceback": None,
        "notes": [],
        "paths": {
            "run_dir": str(run_dir),
            "phase0": str(phase0_path),
            "phase0_latest": str(phase0_latest_path),
            "snapshot": str(snapshot_path),
            "latest": str(latest_path),
            "last_run": str(last_run_path),
            "run": str(run_path),
        },
    }

    try:
        conn = _db_connect()
        try:
            # Phase0
            results: List[dict[str, Any]] = []
            ok_all = True
            for (qname, qsql) in QUERIES:
                r = _run_query(conn, qname, qsql, row_limit=200)
                results.append(r)
                if not r.get("ok"):
                    ok_all = False

            phase0_obj: dict[str, Any] = {
                "_meta": _meta(phase0_path, run_id),
                "ok": ok_all,
                "phase": 0,
                "queries": results,
            }
            _write_json_atomic(phase0_path, phase0_obj, mode=0o644)

            _write_json_atomic(
                phase0_latest_path,
                {
                    "_meta": _meta(phase0_latest_path, run_id),
                    "ok": True,
                    "run_id": run_id,
                    "phase0_path": str(phase0_path),
                    "generated_utc": _utc_iso(),
                },
                mode=0o644,
            )

            # Phase1A (deterministic ops_brief + pointers)
            ops_brief = build_ops_brief(results=results, run_id=run_id)
            try:
                write_phase1_artifacts(
                    write_json_atomic=_write_json_atomic,
                    meta=_meta,
                    root=root,
                    run_dir=run_dir,
                    run_id=run_id,
                    ops_brief=ops_brief,
                )
                rec["notes"].append("phase1A wrote ops_brief + trace + pointer")
            except Exception as e:
                rec["notes"].append(f"phase1A failed: {type(e).__name__}: {e}")

            # Phase2 (LLM findings + pointers). MUST leave artifacts even on failure.
            phase2_dir = run_dir / "phase2"
            try:
                phase2_dir.mkdir(parents=True, exist_ok=True)

                findings_obj, phase2_trace = run_phase2_findings(
                    ops_brief=ops_brief,
                    run_id=run_id,
                    domain_id="missions",
                    pack_name="phase2-missions",
                    out_dir=phase2_dir,
                    max_tokens=int(os.environ.get("TAKS_LLM_MAX_TOKENS") or 450),
                    temperature=0.0,
                )

                p2_findings = phase2_dir / "missions_findings.json"
                p2_trace = phase2_dir / "trace.json"
                _write_json_atomic(p2_findings, findings_obj, mode=0o644)
                _write_json_atomic(p2_trace, phase2_trace, mode=0o644)

                _write_json_atomic(
                    phase2_latest_path,
                    {
                        "_meta": _meta(phase2_latest_path, run_id),
                        "ok": bool(findings_obj.get("ok")) if isinstance(findings_obj, dict) else False,
                        "run_id": run_id,
                        "generated_utc": _utc_iso(),
                        "missions_findings_path": str(p2_findings),
                        "trace_path": str(p2_trace),
                        "prompt_path": str(phase2_dir / "prompt.txt"),
                        "response_path": str(phase2_dir / "response.txt"),
                        "llm_error": phase2_trace.get("llm_error") if isinstance(phase2_trace, dict) else None,
                        "parse": phase2_trace.get("parse") if isinstance(phase2_trace, dict) else None,
                    },
                    mode=0o644,
                )

                rec["notes"].append("phase2 wrote findings + trace + prompt/response + pointer")
            except Exception as e:
                # If something truly unexpected happens, still try to write a minimal pointer so UI updates.
                rec["notes"].append(f"phase2 failed hard: {type(e).__name__}: {e}")
                try:
                    _write_json_atomic(
                        phase2_latest_path,
                        {
                            "_meta": _meta(phase2_latest_path, run_id),
                            "ok": False,
                            "run_id": run_id,
                            "generated_utc": _utc_iso(),
                            "missions_findings_path": str(phase2_dir / "missions_findings.json"),
                            "trace_path": str(phase2_dir / "trace.json"),
                            "prompt_path": str(phase2_dir / "prompt.txt"),
                            "response_path": str(phase2_dir / "response.txt"),
                            "llm_error": f"{type(e).__name__}: {e}",
                        },
                        mode=0o644,
                    )
                except Exception:
                    pass

            # Snapshot MUST be written AFTER phase2_latest is updated (even on failures)
            snapshot_obj = build_snapshot(
                root=root,
                run_dir=run_dir,
                run_id=run_id,
                ok_all=ok_all,
                phase0_path=phase0_path,
                phase0_obj=phase0_obj,
                sha256_bytes=_sha256_bytes,
                meta=_meta,
            )
            _write_json_atomic(snapshot_path, snapshot_obj, mode=0o644)

            # Success record
            rec["ok"] = True
            rec["notes"].append("ran phase0 curated SQL (with rows)")
            rec["notes"].append("KISS generator + phase1A + phase2 + snapshot")
            rec["notes"].append("phase0 OK" if ok_all else "phase0 had errors (see runs/<run_id>/phase0.json)")

            _write_json_atomic(latest_path, rec, mode=0o644)

        finally:
            try:
                conn.close()
            except Exception:
                pass

    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"
        rec["traceback"] = traceback.format_exc(limit=20)

    finally:
        # Release single-flight lock
        try:
            if lock_fd is not None:
                lock_fd.close()
        except Exception:
            pass

        rec["elapsed_ms"] = int((time.time() - t0) * 1000)
        _write_json_atomic(last_run_path, rec, mode=0o644)
        _write_json_atomic(run_path, rec, mode=0o644)

    return rec
import fcntl

if __name__ == "__main__":
    r = run_once()
    print(json.dumps(r, ensure_ascii=False, indent=2, sort_keys=True))
