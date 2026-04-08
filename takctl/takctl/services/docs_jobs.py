from __future__ import annotations

import threading
import time
from typing import Any

from takctl.services.docs_ingest import process_queued_pdf
from takctl.services.docs_paths import ensure_docs_dirs
from takctl.services.docs_registry import list_docs

_worker_lock = threading.Lock()
_worker_thread: threading.Thread | None = None


def _queue_candidates() -> list[dict[str, Any]]:
    ensure_docs_dirs()
    items = list_docs()
    out = [
        dict(x)
        for x in items
        if str((x or {}).get("status") or "").strip().lower() in {"queued", "processing"}
    ]
    out.sort(key=lambda x: (str(x.get("uploaded_at") or ""), str(x.get("doc_id") or "")))
    return out


def _worker_main() -> None:
    global _worker_thread
    try:
        while True:
            items = _queue_candidates()
            if not items:
                return

            doc_id = str(items[0].get("doc_id") or "").strip()
            if not doc_id:
                time.sleep(0.05)
                continue

            try:
                process_queued_pdf(doc_id)
            except Exception:
                # process_queued_pdf is expected to persist failed state itself
                pass

            time.sleep(0.05)
    finally:
        with _worker_lock:
            _worker_thread = None


def start_docs_worker() -> None:
    global _worker_thread
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        t = threading.Thread(target=_worker_main, name="takctl-docs-worker", daemon=True)
        _worker_thread = t
        t.start()
