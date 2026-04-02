from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastembed import TextEmbedding

DOCS_ROOT = Path("/opt/tak/tools/takctl/state/docs")
DERIVED_ROOT = DOCS_ROOT / "derived"

_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_model: TextEmbedding | None = None


def _embedder() -> TextEmbedding:
    global _model
    if _model is None:
        _model = TextEmbedding(model_name=_MODEL_NAME)
    return _model


def vector_index_path(doc_id: str) -> Path:
    return DERIVED_ROOT / doc_id / "vectors.json"


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / ((na ** 0.5) * (nb ** 0.5))


def _embed_texts(texts: list[str]) -> list[list[float]]:
    emb = _embedder()
    out: list[list[float]] = []
    for v in emb.embed(texts):
        out.append([float(x) for x in v.tolist()])
    return out


def build_doc_vector_index(doc_id: str) -> dict[str, Any]:
    chunk_path = DERIVED_ROOT / doc_id / "chunks.jsonl"
    if not chunk_path.exists():
        return {"ok": False, "error": "chunks missing", "doc_id": doc_id}

    rows: list[dict[str, Any]] = []
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

    texts: list[str] = []
    meta: list[dict[str, Any]] = []
    for row in rows:
        title = str(row.get("title") or "")
        section_path = list(row.get("section_path") or [])
        text = str(row.get("text") or "")
        enriched = title + "\n" + " / ".join(str(x) for x in section_path) + "\n" + text
        texts.append(enriched)
        meta.append({
            "chunk_id": str(row.get("chunk_id") or ""),
            "title": title,
            "section_path": section_path,
            "page_start": row.get("page_start"),
            "page_end": row.get("page_end"),
            "text": text[:1600],
        })

    vecs = _embed_texts(texts) if texts else []

    items: list[dict[str, Any]] = []
    for m, v in zip(meta, vecs):
        x = dict(m)
        x["embedding"] = v
        items.append(x)

    out = {
        "doc_id": doc_id,
        "model": _MODEL_NAME,
        "count": len(items),
        "items": items,
    }
    path = vector_index_path(doc_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "doc_id": doc_id, "count": len(items), "path": str(path), "model": _MODEL_NAME}


def ensure_doc_vector_index(doc_id: str) -> dict[str, Any]:
    path = vector_index_path(doc_id)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and str(data.get("doc_id") or "") == doc_id:
                return {
                    "ok": True,
                    "doc_id": doc_id,
                    "count": int(data.get("count") or 0),
                    "path": str(path),
                    "model": str(data.get("model") or ""),
                }
        except Exception:
            pass
    return build_doc_vector_index(doc_id)


def semantic_search_doc(
    *,
    doc_id: str,
    query: str,
    limit: int = 8,
    min_score: float = 0.20,
) -> dict[str, Any]:
    d = str(doc_id or "").strip()
    q = str(query or "").strip()
    if not d:
        return {"ok": False, "error": "doc_id required"}
    if not q:
        return {"ok": False, "error": "query required"}

    ensured = ensure_doc_vector_index(d)
    if not ensured.get("ok"):
        return ensured

    path = vector_index_path(d)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"failed to read vector index: {e}", "doc_id": d}

    qv_list = _embed_texts([q])
    if not qv_list:
        return {"ok": False, "error": "query embedding failed", "doc_id": d}
    qv = qv_list[0]

    lim = max(1, min(int(limit or 8), 20))
    floor = float(min_score)

    hits: list[dict[str, Any]] = []
    for item in list(data.get("items") or []):
        if not isinstance(item, dict):
            continue
        ev = list(item.get("embedding") or [])
        score = _cosine(qv, [float(x) for x in ev])
        if score < floor:
            continue
        hits.append({
            "chunk_id": str(item.get("chunk_id") or ""),
            "title": str(item.get("title") or ""),
            "section_path": list(item.get("section_path") or []),
            "page_start": item.get("page_start"),
            "page_end": item.get("page_end"),
            "score": round(score, 6),
            "text": str(item.get("text") or "")[:1200],
        })

    hits.sort(key=lambda x: (-float(x.get("score") or 0.0), str(x.get("chunk_id") or "")))
    hits = hits[:lim]

    return {
        "ok": True,
        "doc_id": d,
        "query": q,
        "count": len(hits),
        "items": hits,
        "model": str(data.get("model") or _MODEL_NAME),
    }
