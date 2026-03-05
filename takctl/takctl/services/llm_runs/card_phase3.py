from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Tuple

from takctl.services.llm.client import LLMClient


# ------------------------------------------------------------
# Minimal HTML validator
# ------------------------------------------------------------

_ALLOWED_TAGS = {
    "section", "div", "header", "footer",
    "h1", "h2", "h3", "p", "small", "strong", "em",
    "ul", "ol", "li",
    "table", "thead", "tbody", "tr", "th", "td",
    "hr", "br",
}


def _validate_html_fragment(html: str) -> dict:
    html = (html or "").strip()
    if not html:
        return {"ok": False, "error": "empty_html", "root_tag": None}

    m = re.match(r"<\s*([a-zA-Z0-9]+)", html)
    if not m:
        return {"ok": False, "error": "not_html", "root_tag": None}

    root = m.group(1).lower()

    if root not in _ALLOWED_TAGS:
        return {"ok": False, "error": f"forbidden_root:{root}", "root_tag": root}

    tags = re.findall(r"<\s*/?\s*([a-zA-Z0-9]+)", html)
    for t in tags:
        if t.lower() not in _ALLOWED_TAGS:
            return {"ok": False, "error": f"forbidden_tag:{t}", "root_tag": root}

    return {"ok": True, "error": None, "root_tag": root}


# ------------------------------------------------------------
# Prompt pack loader (RUNTIME ONLY)
# ------------------------------------------------------------

def _read_pack(pack_name: str) -> Tuple[str, str]:
    """
    Runtime-only prompt pack resolution.
    """
    base = Path("/opt/tak/tools/takctl/llm/prompt-packs") / pack_name

    sys_p = base / "system.txt"
    usr_p = base / "user.txt"

    if not sys_p.exists() or not usr_p.exists():
        raise FileNotFoundError(f"Prompt pack not found: {base}")

    return (
        sys_p.read_text(encoding="utf-8", errors="replace"),
        usr_p.read_text(encoding="utf-8", errors="replace"),
    )


# ------------------------------------------------------------
# Parse helpers
# ------------------------------------------------------------

def _strip_outer_code_fence(text: str) -> str:
    """
    Best-effort: if text is wrapped in a single outer ```...``` fence, strip it.
    If the model emits just ``` this returns "```" (caller will fail JSON parse).
    """
    t = (text or "").strip()
    if not t.startswith("```"):
        return t
    last = t.rfind("```")
    if last <= 0 or last + 3 != len(t):
        return t
    inner = t[3:last]
    inner2 = inner.lstrip("\r\n")
    lines = inner2.splitlines()
    if lines:
        first = lines[0].strip().lower()
        if first in ("json", "javascript", "js", "text"):
            inner2 = "\n".join(lines[1:])
    return inner2.strip()


def _parse_phase3_json(raw: str) -> Tuple[dict[str, Any] | None, str | None]:
    """
    Returns (obj, err). Expects obj to be a JSON object.
    """
    t = _strip_outer_code_fence(raw)
    try:
        obj = json.loads(t)
    except Exception as e:
        return None, f"json_decode_failed: {type(e).__name__}: {e}"
    if not isinstance(obj, dict):
        return None, "not_object"
    return obj, None


def _extract_html_from_obj(obj: dict[str, Any]) -> Tuple[str, str | None]:
    """
    Accept either:
      - {"html_lines": [str, ...]}
      - {"html": "<div>...</div>"}
    Prefer html_lines.
    """
    if isinstance(obj.get("html_lines"), list):
        lines = []
        for it in obj.get("html_lines") or []:
            if isinstance(it, str) and it.strip():
                lines.append(it.rstrip("\r\n"))
        if not lines:
            return "", "empty_html_lines"
        return "\n".join(lines).strip(), None

    h = obj.get("html")
    if isinstance(h, str) and h.strip():
        return h.strip(), None

    return "", "missing_html"


def _phase3_json_schema() -> dict[str, Any]:
    # Robust “creative but bounded” schema: HTML as lines (preferred) or a single string.
    # NOTE: if your llama.cpp json_schema implementation supports oneOf, keep it simple:
    # we enforce html_lines only to maximize determinism.
    return {
        "type": "object",
        "properties": {
            "html_lines": {
                "type": "array",
                "minItems": 3,
                "items": {"type": "string", "minLength": 1},
            }
        },
        "required": ["html_lines"],
        "additionalProperties": False,
    }


# ------------------------------------------------------------
# Phase3 runner
# ------------------------------------------------------------

def run_phase3_card(
    *,
    run_id: str,
    out_dir: Path,
    pack_name: str,
    phase2_findings_obj: Dict[str, Any],
    max_tokens: int = 900,
    temperature: float = 0.2,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:

    out_dir.mkdir(parents=True, exist_ok=True)

    prompt_path = out_dir / "prompt.txt"
    response_path = out_dir / "response.txt"          # raw model text (verbatim)
    response_http_path = out_dir / "response.http.json"
    response_html_path = out_dir / "response.html"    # joined HTML fragment (best-effort)

    t0 = time.time()

    sys_txt, usr_tpl = _read_pack(pack_name)

    # Embed phase2 JSON into user template
    phase2_json = json.dumps(phase2_findings_obj, ensure_ascii=False, indent=2)
    user_txt = usr_tpl.replace("{{PHASE2_JSON}}", phase2_json)

    # Add a tiny, explicit envelope instruction at the end (do NOT mention markdown/fences)
    user_txt = (
        user_txt.strip()
        + "\n\n"
        + "OUTPUT_FORMAT:\n"
        + "Return a single JSON object with key 'html_lines' (array of strings).\n"
        + "No other text.\n"
    )

    prompt = (sys_txt.strip() + "\n\n" + user_txt.strip()).strip() + "\n"
    prompt_path.write_text(prompt, encoding="utf-8")

    llm = LLMClient(llm_url=(os.environ.get("TAKS_LLM_URL") or "http://127.0.0.1:8090").strip())

    llm_error: str | None = None
    raw = ""
    http_code = 0
    http_body: Any = None
    http_err: str | None = None

    try:
        # Use completions_debug so we can persist verbatim HTTP body like Phase 2 does.
        raw, http_code, http_body, http_err = llm.completions_debug(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            json_schema=_phase3_json_schema(),
        )
        # Persist verbatim HTTP body for debug parity with Phase2
        response_http_path.write_text(json.dumps(http_body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as e:
        llm_error = f"{type(e).__name__}: {e}"
        raw = ""
        try:
            response_http_path.write_text("", encoding="utf-8")
        except Exception:
            pass

    # Persist raw text as-is (even if empty / garbage)
    response_path.write_text(raw or "", encoding="utf-8")

    # Parse JSON -> extract html -> validate
    parse_err: str | None = None
    obj: dict[str, Any] | None = None
    html = ""

    if raw:
        obj, parse_err = _parse_phase3_json(raw)
        if obj is not None and parse_err is None:
            html, parse_err = _extract_html_from_obj(obj)

    # Always write the computed html fragment (empty if failed)
    response_html_path.write_text(html or "", encoding="utf-8")

    chk = _validate_html_fragment(html)

    card_obj: Dict[str, Any] = {
        "contract": {"name": "taks.card_html", "version": 1},
        "ok": chk["ok"],
        "run_id": run_id,
        "root_tag": chk.get("root_tag"),
    }

    if chk["ok"]:
        card_obj["html"] = html.strip()
    else:
        card_obj["error"] = chk["error"]
        if parse_err:
            card_obj["parse_error"] = parse_err
        if http_err:
            card_obj["http_err"] = http_err
        if http_code and http_code != 200:
            card_obj["http_code"] = int(http_code)

    trace_obj: Dict[str, Any] = {
        "ok": chk["ok"] and (llm_error is None) and (parse_err is None) and (http_code in (0, 200)),
        "run_id": run_id,
        "pack": pack_name,
        "llm_error": llm_error,
        "http": {"code": http_code, "err": http_err, "body_type": type(http_body).__name__ if http_body is not None else None},
        "parse_error": parse_err,
        "prompt_path": str(prompt_path),
        "response_path": str(response_path),
        "response_http_path": str(response_http_path),
        "response_html_path": str(response_html_path),
        "elapsed_ms": int((time.time() - t0) * 1000),
    }

    return card_obj, trace_obj
