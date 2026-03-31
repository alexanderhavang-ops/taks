from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DOCS_ROOT = Path("/opt/tak/tools/takctl/state/docs")
REGISTRY_PATH = DOCS_ROOT / "registry" / "docs.json"
DERIVED_ROOT = DOCS_ROOT / "derived"


def _load_registry() -> list[dict[str, Any]]:
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    items = data.get("items") or []
    return [x for x in items if isinstance(x, dict)]


def list_reference_docs(*, only_active: bool = True) -> dict[str, Any]:
    items = _load_registry()
    out: list[dict[str, Any]] = []
    for it in items:
        if only_active and not bool(it.get("active", True)):
            continue
        out.append({
            "doc_id": str(it.get("doc_id") or ""),
            "title": str(it.get("title") or ""),
            "filename": str(it.get("filename") or ""),
            "status": str(it.get("status") or ""),
            "active": bool(it.get("active", True)),
            "chunk_count": int(it.get("chunk_count") or 0),
            "uploaded_at": str(it.get("uploaded_at") or ""),
        })
    out.sort(key=lambda x: x.get("uploaded_at") or "", reverse=True)
    return {"ok": True, "count": len(out), "items": out}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _score(query: str, text: str) -> int:
    q = _norm(query)
    t = _norm(text)
    if not q or not t:
        return 0
    score = 0
    if q in t:
        score += 100
    for term in [x for x in re.split(r"\s+", q) if x]:
        if term in t:
            score += 10
    return score


def search_reference_docs(
    *,
    query: str,
    limit: int = 8,
    doc_id: str = "",
) -> dict[str, Any]:
    q = str(query or "").strip()
    if not q:
        return {"ok": False, "error": "query required"}

    lim = max(1, min(int(limit or 8), 20))
    wanted_doc = str(doc_id or "").strip()

    reg_items = _load_registry()
    reg_by_id = {str(x.get("doc_id") or ""): x for x in reg_items if isinstance(x, dict)}

    hits: list[dict[str, Any]] = []

    for p in sorted(DERIVED_ROOT.glob("*/chunks.jsonl")):
        cur_doc_id = p.parent.name
        if wanted_doc and cur_doc_id != wanted_doc:
            continue

        reg = reg_by_id.get(cur_doc_id) or {}
        if not bool(reg.get("active", True)):
            continue
        if str(reg.get("status") or "") != "ready":
            continue

        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue

        title = str(reg.get("title") or cur_doc_id)
        for line in lines:
            try:
                row = json.loads(line)
            except Exception:
                continue
            text = str(row.get("text") or "")
            chunk_id = str(row.get("chunk_id") or "")
            score = _score(q, title + "\n" + text)
            if score <= 0:
                continue
            hits.append({
                "doc_id": cur_doc_id,
                "title": title,
                "chunk_id": chunk_id,
                "score": score,
                "text": text[:1200],
            })

    hits.sort(key=lambda x: (-int(x.get("score") or 0), str(x.get("doc_id") or ""), str(x.get("chunk_id") or "")))
    hits = hits[:lim]

    return {
        "ok": True,
        "query": q,
        "count": len(hits),
        "items": hits,
    }


def get_reference_doc_context(
    *,
    doc_id: str,
    chunk_id: str,
    window: int = 1,
) -> dict[str, Any]:
    d = str(doc_id or "").strip()
    c = str(chunk_id or "").strip()
    if not d:
        return {"ok": False, "error": "doc_id required"}
    if not c:
        return {"ok": False, "error": "chunk_id required"}

    reg_items = _load_registry()
    reg_by_id = {str(x.get("doc_id") or ""): x for x in reg_items if isinstance(x, dict)}
    reg = reg_by_id.get(d) or {}
    if not reg:
        return {"ok": False, "error": "document not found", "doc_id": d}
    if str(reg.get("status") or "") != "ready":
        return {"ok": False, "error": "document not ready", "doc_id": d}

    chunk_path = DERIVED_ROOT / d / "chunks.jsonl"
    if not chunk_path.exists():
        return {"ok": False, "error": "chunks missing", "doc_id": d}

    rows: list[dict[str, Any]] = []
    try:
        for line in chunk_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if isinstance(row, dict):
                rows.append(row)
    except Exception as e:
        return {"ok": False, "error": f"failed to read chunks: {e}", "doc_id": d}

    idx = -1
    for i, row in enumerate(rows):
        if str(row.get("chunk_id") or "") == c:
            idx = i
            break

    if idx < 0:
        return {"ok": False, "error": "chunk not found", "doc_id": d, "chunk_id": c}

    w = max(0, min(int(window or 1), 3))
    lo = max(0, idx - w)
    hi = min(len(rows), idx + w + 1)

    items: list[dict[str, Any]] = []
    for i in range(lo, hi):
        row = rows[i]
        items.append({
            "chunk_id": str(row.get("chunk_id") or ""),
            "is_focus": i == idx,
            "text": str(row.get("text") or "")[:2200],
            "section_path": list(row.get("section_path") or []),
            "page_start": row.get("page_start"),
            "page_end": row.get("page_end"),
        })

    focus = rows[idx]
    return {
        "ok": True,
        "doc_id": d,
        "title": str(reg.get("title") or d),
        "chunk_id": c,
        "window": w,
        "items": items,
        "focus_text": str(focus.get("text") or "")[:2200],
    }
