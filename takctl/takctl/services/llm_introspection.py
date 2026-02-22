from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Optional

# Hard bounds so debug can never DOS your disk/browser
_MAX_TEXT = 256_000          # per artifact/state/events chunk
_MAX_EVENT_LINE = 24_000     # per event line


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _json_default(o: Any) -> Any:
    if is_dataclass(o):
        return asdict(o)
    return str(o)


def _safe_json(obj: Any) -> str:
    return json.dumps(obj, default=_json_default, ensure_ascii=False, indent=2, sort_keys=True)


def state_root(view: str) -> Path:
    base = (os.environ.get("TAKCTL_STATE_DIR") or "").strip() or "/opt/tak/tools/takctl/state"
    p = Path(base) / "llm" / view
    p.mkdir(parents=True, exist_ok=True)
    (p / "artifacts").mkdir(parents=True, exist_ok=True)
    return p


def _write_atomic(path: Path, data: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_bytes(data)
    os.chmod(tmp, mode)
    tmp.replace(path)


def write_state(view: str, phase: str, **kv: Any) -> None:
    """
    Writes {ts_utc, view, phase, ...} to <state_root>/debug_state.json (atomic).
    """
    root = state_root(view)
    obj = {"ts_utc": _now_iso(), "view": view, "phase": str(phase)}
    obj.update(kv)
    raw = _safe_json(obj)
    if len(raw) > _MAX_TEXT:
        raw = raw[:_MAX_TEXT] + "\n…(truncated)\n"
    _write_atomic(root / "debug_state.json", raw.encode("utf-8", "ignore"))


def append_event(view: str, event: str, **kv: Any) -> None:
    """
    Appends one JSONL line to <state_root>/debug_events.jsonl.
    Keep it bounded (per-line), but do not truncate file here.
    """
    root = state_root(view)
    obj = {"ts_utc": _now_iso(), "view": view, "event": str(event)}
    obj.update(kv)
    line = json.dumps(obj, default=_json_default, ensure_ascii=False, sort_keys=True)
    if len(line) > _MAX_EVENT_LINE:
        line = line[:_MAX_EVENT_LINE] + "…(truncated)"
    with (root / "debug_events.jsonl").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def write_artifact_text(view: str, name: str, text: str, *, content_type: str = "text/plain") -> None:
    """
    Writes an artifact into <state_root>/artifacts/<name>.<ext>
    and records a small sidecar <name>.meta.json.
    """
    root = state_root(view)
    safe = "".join(c for c in (name or "").strip() if c.isalnum() or c in ("-", "_", ".", "@"))
    if not safe:
        safe = "artifact"
    if "." not in safe:
        safe = safe + ".txt"

    body = (text or "")
    if len(body) > _MAX_TEXT:
        body = body[:_MAX_TEXT] + "\n…(truncated)\n"

    art_path = root / "artifacts" / safe
    _write_atomic(art_path, body.encode("utf-8", "ignore"))

    meta = {
        "ts_utc": _now_iso(),
        "view": view,
        "name": safe,
        "content_type": content_type,
        "bytes": art_path.stat().st_size if art_path.exists() else None,
    }
    _write_atomic(
        art_path.with_suffix(art_path.suffix + ".meta.json"),
        _safe_json(meta).encode("utf-8", "ignore"),
    )


def list_artifacts(view: str) -> list[dict[str, Any]]:
    root = state_root(view)
    d = root / "artifacts"
    out: list[dict[str, Any]] = []
    if not d.exists():
        return out
    for p in sorted(d.iterdir()):
        if p.is_dir():
            continue
        if p.name.endswith(".meta.json"):
            continue
        meta_p = p.with_suffix(p.suffix + ".meta.json")
        meta = None
        if meta_p.exists():
            try:
                meta = json.loads(meta_p.read_text(encoding="utf-8"))
            except Exception:
                meta = None
        out.append({"name": p.name, "bytes": p.stat().st_size, "meta": meta})
    return out


def read_artifact(view: str, name: str) -> tuple[Optional[Path], Optional[dict[str, Any]]]:
    root = state_root(view)
    safe = "".join(c for c in (name or "").strip() if c.isalnum() or c in ("-", "_", ".", "@"))
    if not safe:
        return None, None
    p = root / "artifacts" / safe
    if not p.exists() or not p.is_file():
        return None, None
    meta_p = p.with_suffix(p.suffix + ".meta.json")
    meta = None
    if meta_p.exists():
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
        except Exception:
            meta = None
    return p, meta


def tail_events(view: str, tail: int = 200) -> list[dict[str, Any]]:
    root = state_root(view)
    p = root / "debug_events.jsonl"
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    lines = lines[-max(1, int(tail)) :]
    out: list[dict[str, Any]] = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            out.append({"ts_utc": None, "view": view, "event": "unparseable_line", "raw": ln[:500]})
    return out
