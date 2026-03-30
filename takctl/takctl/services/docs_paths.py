from __future__ import annotations

from pathlib import Path

DOCS_ROOT = Path("/opt/tak/tools/takctl/state/docs")
DOCS_REGISTRY_DIR = DOCS_ROOT / "registry"
DOCS_RAW_DIR = DOCS_ROOT / "raw"
DOCS_DERIVED_DIR = DOCS_ROOT / "derived"
DOCS_INDEX_DIR = DOCS_ROOT / "index"


def registry_path() -> Path:
    return DOCS_REGISTRY_DIR / "docs.json"


def raw_doc_dir(doc_id: str) -> Path:
    return DOCS_RAW_DIR / str(doc_id).strip()


def derived_doc_dir(doc_id: str) -> Path:
    return DOCS_DERIVED_DIR / str(doc_id).strip()


def raw_original_path(doc_id: str, filename: str = "original.pdf") -> Path:
    return raw_doc_dir(doc_id) / filename


def manifest_path(doc_id: str) -> Path:
    return derived_doc_dir(doc_id) / "manifest.json"


def status_path(doc_id: str) -> Path:
    return derived_doc_dir(doc_id) / "status.json"


def extract_path(doc_id: str) -> Path:
    return derived_doc_dir(doc_id) / "extract.txt"


def sections_path(doc_id: str) -> Path:
    return derived_doc_dir(doc_id) / "sections.json"


def chunks_path(doc_id: str) -> Path:
    return derived_doc_dir(doc_id) / "chunks.jsonl"


def errors_path(doc_id: str) -> Path:
    return derived_doc_dir(doc_id) / "errors.log"


def ensure_docs_dirs() -> None:
    DOCS_REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_RAW_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_INDEX_DIR.mkdir(parents=True, exist_ok=True)
