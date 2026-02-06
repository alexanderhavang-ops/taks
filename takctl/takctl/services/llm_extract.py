from __future__ import annotations

import json
from typing import Any, Tuple


def strip_code_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        parts = t.split("```", 2)
        if len(parts) >= 2:
            t = parts[1]
    return t.strip()


def extract_json_from_text(text: str) -> Tuple[dict[str, Any] | None, str | None, str | None]:
    """
    Attempt to extract the first valid JSON object from arbitrary text.

    Returns:
      (parsed_json | None, error | None, json_candidate | None)
    """
    if not text:
        return None, "empty_text", None

    candidate = strip_code_fences(text)

    # Fast path: entire content is JSON
    try:
        obj = json.loads(candidate)
        if isinstance(obj, dict):
            return obj, None, candidate
    except Exception:
        pass

    # Heuristic: find first {...} block
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        fragment = candidate[start : end + 1]
        try:
            obj = json.loads(fragment)
            if isinstance(obj, dict):
                return obj, None, fragment
        except Exception as e:
            return None, repr(e), fragment

    return None, "no_json_object_found", candidate
