from __future__ import annotations

import json
import os
import re
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
# Sanitize LLM output
# ------------------------------------------------------------

def _sanitize_html_fragment(raw: str) -> str:
    """
    Make HTML parsing resilient to common llama.cpp quirks:
      - multiple leading markdown fences
      - ```html / ``` blocks
      - stray empty fenced blocks before the real output
      - trailing fence
      - extra surrounding whitespace/blank lines
    """
    t = (raw or "").strip()
    if not t:
        return t

    # Drop any number of leading fence lines and blank lines.
    # Example seen:
    #   ```\n\n```html\n<div>...</div>\n```
    for _ in range(10):  # bounded
        u = t.lstrip()
        if u.startswith("```"):
            lines = u.splitlines()
            lines = lines[1:] if lines else []
            t = "\n".join(lines).strip()
            continue
        if t.startswith("\n"):
            t = t.lstrip("\n").strip()
            continue
        break

    # Drop trailing fence if present (after trimming blank lines)
    lines = t.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and lines[-1].strip() == "```":
        lines.pop()

    t = "\n".join(lines).strip()
    return t


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
    response_path = out_dir / "response.html"

    sys_txt, usr_tpl = _read_pack(pack_name)

    phase2_json = json.dumps(phase2_findings_obj, ensure_ascii=False, indent=2)
    user_txt = usr_tpl.replace("{{PHASE2_JSON}}", phase2_json)

    prompt = (sys_txt.strip() + "\n\n" + user_txt.strip()).strip() + "\n"
    prompt_path.write_text(prompt, encoding="utf-8")

    llm = LLMClient(llm_url=os.environ.get("LLM_URL", "http://127.0.0.1:8090"))

    llm_error = None
    html = ""

    try:
        raw = llm.completions_text(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        html = _sanitize_html_fragment(raw)
    except Exception as e:
        llm_error = f"{type(e).__name__}: {e}"
        html = ""

    response_path.write_text(html or "", encoding="utf-8")

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

    trace_obj: Dict[str, Any] = {
        "ok": chk["ok"] and (llm_error is None),
        "run_id": run_id,
        "pack": pack_name,
        "llm_error": llm_error,
        "parse": chk,
        "prompt_path": str(prompt_path),
        "response_path": str(response_path),
    }

    return card_obj, trace_obj
