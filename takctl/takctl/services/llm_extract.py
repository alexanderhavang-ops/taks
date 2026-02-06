from __future__ import annotations

import json
from typing import Any, Tuple


def strip_code_fences(text: str) -> str:
    """
    Remove a single surrounding Markdown code fence if present.
    Handles ```json ... ``` and ``` ... ```.
    Conservative: only strips the outermost fence once.
    """
    t = (text or "").strip()
    if not t.startswith("```"):
        return t

    parts = t.split("```", 2)
    if len(parts) < 3:
        return t.strip()

    inner = parts[1]
    inner_lines = inner.splitlines()
    if inner_lines:
        first = inner_lines[0].strip().lower()
        if first in ("json", "javascript", "js", "text", "yaml", "yml"):
            inner = "\n".join(inner_lines[1:])

    return inner.strip()


def extract_json_from_text(
    text: str,
) -> Tuple[dict[str, Any] | None, str | None, str | None]:
    """
    Extract the first valid JSON object (dict) from arbitrary text.

    Returns:
        (parsed_dict | None, error | None, json_candidate | None)

    Strategy:
      1) Strip code fences
      2) Try json.loads on whole text
      3) Scan for embedded JSON using JSONDecoder.raw_decode
      4) Last-resort trimming from first '{'
    """
    if not text:
        return None, "empty_text", None

    candidate = strip_code_fences(text)

    # --- 1) Fast path: whole string is JSON
    try:
        obj = json.loads(candidate)
        if isinstance(obj, dict):
            return obj, None, candidate
    except Exception:
        pass

    dec = json.JSONDecoder()

    # --- 2) Scan for embedded JSON objects inside prose
    for i, ch in enumerate(candidate):
        if ch != "{":
            continue
        try:
            val, end = dec.raw_decode(candidate, i)
        except Exception:
            continue
        if isinstance(val, dict):
            fragment = candidate[i:end]
            return val, None, fragment

    # --- 3) Last resort: trim tail progressively
    start = candidate.find("{")
    if start != -1:
        tail = candidate[start:]
        max_trim = min(2000, len(tail))
        for trim in range(0, max_trim):
            s = tail[:-trim] if trim else tail
            try:
                val, end = dec.raw_decode(s, 0)
            except Exception:
                continue
            if isinstance(val, dict):
                fragment = s[:end]
                return val, None, fragment

    return None, "no_json_object_found", candidate

