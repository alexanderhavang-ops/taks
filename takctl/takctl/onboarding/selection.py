from __future__ import annotations

import json
from pathlib import Path

ARTIFACT_ROOT = Path("/opt/tak/takctl-state/onboarding/artifacts")


def artifact_root(username: str) -> Path:
    return ARTIFACT_ROOT / username


def _selection_path(username: str) -> Path:
    return artifact_root(username) / "selection.json"


def load_selection(username: str) -> dict:
    p = _selection_path(username)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_selection(username: str, sel: dict) -> None:
    out = _selection_path(username)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(sel, indent=2, sort_keys=True) + "\n", encoding="utf-8")
