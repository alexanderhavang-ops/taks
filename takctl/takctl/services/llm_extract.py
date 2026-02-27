from __future__ import annotations

import json
from typing import Any, Tuple


def strip_code_fences(text: str) -> str:
    """
    Remove a single surrounding Markdown code fence if present.

    IMPORTANT:
    LLMs sometimes emit *multiple* fences, e.g.:
        ```\n\n```json\n{...}\n```

    The old implementation used split("```", 2) which can accidentally keep only the
    empty middle part and discard the actual JSON.

    This version strips ONLY the outermost fence when the text both starts with ```
    and ends with ``` (after whitespace trim). It uses rfind to locate the final fence.
    """
    t = (text or "").strip()
    if not t.startswith("```"):
        return t

    last = t.rfind("```")
    # Need a distinct closing fence at the very end
    if last <= 0 or last + 3 != len(t):
        return t

    inner = t[3:last]

    # Drop an optional language line immediately after the opening fence.
    inner2 = inner.lstrip("\r\n")
    lines = inner2.splitlines()
    if lines:
        first = lines[0].strip().lower()
        if first in ("json", "javascript", "js", "text", "yaml", "yml"):
            inner2 = "\n".join(lines[1:])

    return inner2.strip()


def extract_json_from_text(
    text: str,
) -> Tuple[dict[str, Any] | None, str | None, str | None]:
    """
    Extract the first valid JSON object (dict) from arbitrary text.

    Returns:
        (parsed_dict | None, error | None, json_candidate | None)
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
