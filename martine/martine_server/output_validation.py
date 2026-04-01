from __future__ import annotations

import json
from typing import Any


def extract_first_json_object(text: str) -> str:
    s = (text or '').strip()
    if not s:
        raise ValueError('empty_text')
    i0 = s.find('{')
    if i0 < 0:
        raise ValueError('no_json_start')
    s = s[i0:]
    depth = 0
    in_str = False
    esc = False
    for idx, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
                continue
            if ch == '\\':
                esc = True
                continue
            if ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == '{':
            depth += 1
            continue
        if ch == '}':
            depth -= 1
            if depth == 0:
                return s[:idx+1]
    raise ValueError('unterminated_json')


def parse_structured_json(text: str) -> dict[str, Any]:
    raw = extract_first_json_object(text)
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError('json_not_object')
    return obj
