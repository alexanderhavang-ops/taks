from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


def _load_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _read_text_if_exists(p: Path) -> Optional[str]:
    try:
        if p.exists():
            return p.read_text(encoding="utf-8")
    except Exception:
        return None


def _read_bytes_if_exists(p: Path) -> Optional[bytes]:
    try:
        if p.exists():
            return p.read_bytes()
    except Exception:
        return None


def _extract_phase2_paths(obj: Any) -> tuple[str, str, str, str, str]:
    """
    Best-effort extraction of prompt/response/trace/findings/http paths from either:
      - per-run trace.json (preferred)
      - root pointer phase2_latest.json (fallback)
    Returns (prompt_path, response_path, trace_path, missions_findings_path, response_http_path) as strings (may be empty).
    """
    if not isinstance(obj, dict):
        return "", "", "", "", ""

    files = obj.get("files")
    if isinstance(files, dict):
        pp = str(files.get("prompt_path") or "").strip()
        rp = str(files.get("response_path") or "").strip()
        hp = str(files.get("response_http_path") or "").strip()
    else:
        pp = str(obj.get("prompt_path") or "").strip()
        rp = str(obj.get("response_path") or "").strip()
        hp = ""

    tp = str(obj.get("trace_path") or "").strip()
    mf = str(obj.get("missions_findings_path") or "").strip()

    tr = obj.get("trace_ref")
    if isinstance(tr, dict):
        pp = pp or str(tr.get("prompt_path") or "").strip()
        rp = rp or str(tr.get("response_path") or "").strip()

    return pp, rp, tp, mf, hp


def build_snapshot(
    *,
    root: Path,
    run_dir: Path,
    run_id: str,
    ok_all: bool,
    phase0_path: Path,
    phase0_obj: dict[str, Any],
    sha256_bytes,
    meta,
) -> dict[str, Any]:
    """
    Snapshot is what the UI reads. It MUST reflect *this run* first.
    It may fall back to root pointers for backward compatibility, but only if
    per-run artifacts don't exist.
    """
    snapshot_phase1_latest_obj = None
    snapshot_phase2_latest_obj = None
    snapshot_phase3_latest_obj = None

    snapshot_phase1_obj = None
    snapshot_phase2_obj = None
    snapshot_phase3_obj = None

    snapshot_phase1_path = None
    snapshot_phase2_path = None
    snapshot_phase3_path = None

    phase2_prompt_text = None
    phase2_response_text = None
    phase2_prompt_sha256 = None
    phase2_response_sha256 = None

    phase2_response_http_text = None
    phase2_response_http_sha256 = None

    phase3_prompt_text = None
    phase3_response_text = None
    phase3_prompt_sha256 = None
    phase3_response_sha256 = None

    # ---- Phase1 (current run) ----
    try:
        p1 = run_dir / "phase1" / "missions_brief.json"
        t1 = run_dir / "phase1" / "trace.json"
        if p1.exists():
            snapshot_phase1_path = str(p1)
            snapshot_phase1_obj = _load_json(p1)
            if t1.exists():
                snapshot_phase1_latest_obj = {
                    "ok": True,
                    "run_id": run_id,
                    "missions_brief_path": str(p1),
                    "trace_path": str(t1),
                }
    except Exception:
        pass

    # ---- Phase2 (current run) ----
    try:
        p2 = run_dir / "phase2" / "missions_findings.json"
        t2 = run_dir / "phase2" / "trace.json"
        if p2.exists():
            snapshot_phase2_path = str(p2)
            snapshot_phase2_obj = _load_json(p2)
        if t2.exists():
            snapshot_phase2_latest_obj = _load_json(t2)
    except Exception:
        pass

    # ---- Phase3 (current run) ----
    try:
        p3 = run_dir / "phase3" / "card.html.json"
        t3 = run_dir / "phase3" / "trace.json"
        if p3.exists():
            snapshot_phase3_path = str(p3)
            snapshot_phase3_obj = _load_json(p3)
        if t3.exists():
            snapshot_phase3_latest_obj = _load_json(t3)
    except Exception:
        pass

    # ---- Fallback: root pointers (old deployments) ----
    if snapshot_phase1_latest_obj is None:
        try:
            _p1 = root / "phase1_latest.json"
            if _p1.exists():
                snapshot_phase1_latest_obj = _load_json(_p1)
                snapshot_phase1_path = str(snapshot_phase1_latest_obj.get("missions_brief_path") or "").strip() or snapshot_phase1_path
                if snapshot_phase1_obj is None and snapshot_phase1_path and Path(snapshot_phase1_path).exists():
                    snapshot_phase1_obj = _load_json(Path(snapshot_phase1_path))
        except Exception:
            pass

    # ---- Phase2 embed: verbatim prompt/response + verbatim HTTP body ----
    try:
        pp = rp = tp = mf = hp = ""
        if snapshot_phase2_latest_obj is not None:
            pp, rp, tp, mf, hp = _extract_phase2_paths(snapshot_phase2_latest_obj)

        if not (pp or rp or mf or hp):
            p2_latest = root / "phase2_latest.json"
            if p2_latest.exists():
                p2_latest_obj = _load_json(p2_latest)
                pp2, rp2, tp2, mf2, hp2 = _extract_phase2_paths(p2_latest_obj)
                pp = pp or pp2
                rp = rp or rp2
                mf = mf or mf2
                hp = hp or hp2
                if snapshot_phase2_latest_obj is None:
                    snapshot_phase2_latest_obj = p2_latest_obj
                snapshot_phase2_path = mf or snapshot_phase2_path

        if pp:
            b = _read_bytes_if_exists(Path(pp))
            if b is not None:
                phase2_prompt_sha256 = sha256_bytes(b)
                phase2_prompt_text = b.decode("utf-8", "replace")

        if rp:
            b = _read_bytes_if_exists(Path(rp))
            if b is not None:
                phase2_response_sha256 = sha256_bytes(b)
                phase2_response_text = b.decode("utf-8", "replace")

        if hp:
            b = _read_bytes_if_exists(Path(hp))
            if b is not None:
                phase2_response_http_sha256 = sha256_bytes(b)
                phase2_response_http_text = b.decode("utf-8", "replace")

        if mf and snapshot_phase2_obj is None and Path(mf).exists():
            snapshot_phase2_obj = _load_json(Path(mf))
        snapshot_phase2_path = mf or snapshot_phase2_path

        if snapshot_phase2_latest_obj is None and tp and Path(tp).exists():
            snapshot_phase2_latest_obj = _load_json(Path(tp))
    except Exception:
        pass

    # ---- Phase3 fallback pointer (old deployments) ----
    if snapshot_phase3_latest_obj is None:
        try:
            _p3 = root / "phase3_latest.json"
            if _p3.exists():
                snapshot_phase3_latest_obj = _load_json(_p3)
        except Exception:
            pass

    # ---- Phase3 embed prompt/response ----
    try:
        if snapshot_phase3_latest_obj is not None:
            pp3 = snapshot_phase3_latest_obj.get("prompt_path")
            rp3 = snapshot_phase3_latest_obj.get("response_path")

            if isinstance(pp3, str) and pp3:
                b = _read_bytes_if_exists(Path(pp3))
                if b is not None:
                    phase3_prompt_sha256 = sha256_bytes(b)
                    phase3_prompt_text = b.decode("utf-8", "replace")

            if isinstance(rp3, str) and rp3:
                b = _read_bytes_if_exists(Path(rp3))
                if b is not None:
                    phase3_response_sha256 = sha256_bytes(b)
                    phase3_response_text = b.decode("utf-8", "replace")
    except Exception:
        pass

    return {
        "_meta": meta(root / "snapshot.json", run_id),
        "ok": ok_all,
        "run_id": run_id,
        "phase0_path": str(phase0_path),
        "phase0": phase0_obj,
        "phase1_latest": snapshot_phase1_latest_obj,
        "phase1_path": snapshot_phase1_path,
        "phase1": snapshot_phase1_obj,
        "phase2_latest": snapshot_phase2_latest_obj,
        "phase2_path": snapshot_phase2_path,
        "phase2": snapshot_phase2_obj,
        "phase2_prompt_sha256": phase2_prompt_sha256,
        "phase2_response_sha256": phase2_response_sha256,
        "phase2_prompt_text": phase2_prompt_text,
        "phase2_response_text": phase2_response_text,
        "phase2_response_http_sha256": phase2_response_http_sha256,
        "phase2_response_http_text": phase2_response_http_text,
        "phase3_latest": snapshot_phase3_latest_obj,
        "phase3_path": snapshot_phase3_path,
        "phase3": snapshot_phase3_obj,
        "phase3_prompt_sha256": phase3_prompt_sha256,
        "phase3_response_sha256": phase3_response_sha256,
        "phase3_prompt_text": phase3_prompt_text,
        "phase3_response_text": phase3_response_text,
    }
