from __future__ import annotations

import json
from typing import Any

from takctl.services.docs_paths import ensure_docs_dirs, registry_path


def _default_registry() -> dict[str, Any]:
    return {"items": []}


def load_docs_registry() -> dict[str, Any]:
    ensure_docs_dirs()
    p = registry_path()
    if not p.exists():
        return _default_registry()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return _default_registry()
    if not isinstance(data, dict):
        return _default_registry()
    items = data.get("items")
    if not isinstance(items, list):
        data["items"] = []
    return data


def save_docs_registry(reg: dict[str, Any]) -> None:
    ensure_docs_dirs()
    p = registry_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def list_docs() -> list[dict[str, Any]]:
    reg = load_docs_registry()
    items = reg.get("items") or []
    out = [x for x in items if isinstance(x, dict)]
    out.sort(key=lambda x: str(x.get("uploaded_at") or ""), reverse=True)
    return out


def get_doc(doc_id: str) -> dict[str, Any] | None:
    x = str(doc_id or "").strip()
    if not x:
        return None
    for item in list_docs():
        if str(item.get("doc_id") or "") == x:
            return item
    return None


def upsert_doc(entry: dict[str, Any]) -> None:
    reg = load_docs_registry()
    items = [x for x in (reg.get("items") or []) if isinstance(x, dict)]
    doc_id = str(entry.get("doc_id") or "").strip()
    if not doc_id:
        raise ValueError("missing doc_id")
    replaced = False
    for i, item in enumerate(items):
        if str(item.get("doc_id") or "") == doc_id:
            items[i] = dict(entry)
            replaced = True
            break
    if not replaced:
        items.append(dict(entry))
    reg["items"] = items
    save_docs_registry(reg)


def delete_doc_entry(doc_id: str) -> bool:
    reg = load_docs_registry()
    items = [x for x in (reg.get("items") or []) if isinstance(x, dict)]
    x = str(doc_id or "").strip()
    new_items = [item for item in items if str(item.get("doc_id") or "") != x]
    changed = len(new_items) != len(items)
    reg["items"] = new_items
    save_docs_registry(reg)
    return changed
