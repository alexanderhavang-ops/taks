from __future__ import annotations

import json
from typing import Any, Tuple


def strip_code_fences(text: str) -> str:
    """
    Remove a single surrounding Markdown code fence if present.
    Handles ```json ... ``` and ``` ... ```.

    Note: intentionally conservative; we do not try to strip multiple fences.
    """
    t = (text or "").strip()
    if not t.startswith("```"):
        return t

    # Split into: ```lang?\n ... \n```
    # We only strip the outermost fence.
    parts = t.split("```", 2)
    if len(parts) < 3:
        return t.strip()

    # parts[1] may start with "json\n" or just "\n"
    inner = parts[1]
    # Drop a leading language tag on the first line if present
    inner_lines = inner.splitlines()
    if inner_lines:
        first = inner_lines[0].strip().lower()
        if first in ("json", "javascript", "js", "text", "yaml", "yml"):
            inner = "\n".join(inner_lines[1:])

    return inner.strip()


def extract_json_from_text(text: str) -> Tuple[dict[str, Any] | None, str | None, str | None]:
    """
    Extract the first valid JSON object (a dict) from arbitrary text.

    Returns: (parsed_dict | None, error | None, json_candidate | None)

    Strategy:
      1) Strip code fences.
      2) Try direct json.loads().
      3) Otherwise, scan for each '{' and use JSONDecoder.raw_decode()
         to parse the first valid JSON value at that position.
         We accept the first decoded value that is a dict.
    """
    if not text:
        return None, "empty_text", None

    candidate = strip_code_fences(text)

    # Fast path: the entire content is JSON
    try:
        obj = json.loads(candidate)
        if isinstance(obj, dict):
            return obj, None, candidate
    except Exception:
        pass

    dec = json.JSONDecoder()

    # Scan for JSON objects embedded in prose.
    # raw_decode requires the JSON value to start exactly at idx.
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

    # As a last resort, try a bounded substring (sometimes trailing junk breaks raw_decode scanning)
    # Find first '{' and attempt to decode progressively shorter suffixes by trimming the end.
    start = candidate.find("{")
    if start != -1:
        tail = candidate[start:]
        # Limit work: try trimming at most 2000 chars from the end (for huge outputs)
        max_trim = min(2000, len(tail))
        for trim in range(0, max_trim):
            try:
                val, end = dec.raw_decode(tail[:-trim] if trim else tail, 0)
            except Exception:
                continue
            if isinstance(val, dict):
                fragment = (tail[:-trim] if trim else tail)[:end]
                return val, None, fragment

    return None, "no_json_object_found", candidate
