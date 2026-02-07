from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException

from takctl.config import load_config
from takctl.infra.db import DB
from takctl.services.llm_http import http_post_json
from takctl.services.llm import llm_status

router = APIRouter(prefix="/api/llm", tags=["llm"])


# -----------------------------------------------------------------------------
# Safety / SQL controls
# -----------------------------------------------------------------------------

_SQL_FORBIDDEN = re.compile(
    r"\b("
    r"insert|update|delete|drop|alter|truncate|create|grant|revoke|vacuum|analyze|"
    r"copy|call|do|execute|prepare|deallocate|listen|notify|"
    r"pg_read_file|pg_write_file|pg_ls_dir|lo_import|lo_export"
    r")\b",
    re.IGNORECASE,
)

_SQL_ALLOWED_PREFIX = re.compile(r"^\s*(with\b|select\b)", re.IGNORECASE)

def _sanitize_sql(sql: str) -> str:
    s = (sql or "").strip()
    # block multiple statements / sneaky ';'
    if ";" in s:
        raise ValueError("SQL must be a single statement (no ';').")
    if not _SQL_ALLOWED_PREFIX.match(s):
        raise ValueError("Only SELECT/WITH queries are allowed.")
    if _SQL_FORBIDDEN.search(s):
        raise ValueError("Forbidden keyword detected in SQL.")
    return s


def _rows_to_json(rows: list[tuple], max_rows: int = 50, max_cell_chars: int = 500) -> list[list[Any]]:
    out: list[list[Any]] = []
    for r in rows[: max_rows]:
        row: list[Any] = []
        for c in r:
            if c is None:
                row.append(None)
            else:
                s = str(c)
                if len(s) > max_cell_chars:
                    s = s[:max_cell_chars] + "…"
                row.append(s)
        out.append(row)
    return out


# -----------------------------------------------------------------------------
# LLM tool-loop protocol (JSON)
# -----------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an assistant for a TAK server operator.

You have access to a PostgreSQL database that backs a TAK Server. You do NOT know the schema upfront.
You can explore it safely via SELECT queries (including information_schema and pg_catalog).

Hard rules:
- You MUST only use read-only SQL (SELECT/WITH).
- Always add LIMIT to queries that can return many rows.
- Prefer narrow, incremental queries: discover tables, then columns, then sample rows.
- Never speculate about schema. If unsure, query system catalogs to confirm.

You will be asked to answer operator questions. When you need data, request SQL.
When you have enough data, produce a final answer.

Protocol:
Return ONLY JSON (no prose outside JSON). One of:

1) Ask for SQL:
{"action":"sql","sql":"SELECT ... LIMIT 50","note":"why you need it"}

2) Final:
{"action":"final","answer":"...","evidence":[...optional...],"notes":[...optional...]}

Keep SQL single-statement (no semicolons)."""

# This is the loop "state" we provide back to the model each step.
def _tool_state_to_prompt(user_prompt: str, history: list[dict[str, Any]]) -> str:
    return (
        "USER_QUESTION:\n"
        f"{user_prompt.strip()}\n\n"
        "TOOL_HISTORY:\n"
        + json.dumps(history, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n\n"
        "Remember: output ONLY JSON for the protocol."
    )


def _call_llama_completions(llm_url: str, model: str, prompt: str, max_tokens: int) -> tuple[int, Optional[str], Optional[str]]:
    # llama.cpp server is OpenAI-ish but we rely on /v1/completions (chat may be missing)
    req = {
        "model": model,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "stream": False,
        # keep it deterministic-ish
        "temperature": 0.0,
    }
    code, body, err = http_post_json(f"{llm_url.rstrip('/')}/v1/completions", req, timeout_sec=60.0)
    if code != 200 or not isinstance(body, dict):
        return code, None, err or "bad_response"
    try:
        text = ((body.get("choices") or [{}])[0] or {}).get("text")
        return 200, (text if isinstance(text, str) else None), None
    except Exception as e:
        return 200, None, f"parse_error: {type(e).__name__}: {e}"


def _extract_json_obj(text: str) -> dict[str, Any]:
    """
    Best-effort: pull the first JSON object from the model output.
    """
    raw = (text or "").strip()
    if not raw:
        raise ValueError("empty model output")

    # common case: model outputs leading whitespace then '{...}'
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object found")

    cand = raw[start : end + 1]
    return json.loads(cand)


# -----------------------------------------------------------------------------
# API
# -----------------------------------------------------------------------------

@dataclass
class ChatResult:
    ok: bool
    mode: str
    llm: dict[str, Any]
    steps: list[dict[str, Any]]
    final: dict[str, Any]


@router.post("/chat")
def api_llm_chat(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    """
    llmchat: "Any prompt here" with optional SQL tool-loop.

    payload:
      - prompt: str (required)
      - mode: "direct" | "sql" | "tool" (default "tool")
          direct: prompt -> LLM text (no SQL execution)
          sql:     one-shot (LLM must return {"action":"sql",...} once, we execute, then ask for final)
          tool:    multi-step loop until final or max_steps
      - model: str (default "local-small")
      - max_steps: int (default 4)
      - max_rows: int (default 50)
      - max_tokens: int (default 350)
    """
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    mode = str(payload.get("mode") or "tool").strip().lower()
    if mode not in ("direct", "sql", "tool"):
        raise HTTPException(status_code=400, detail="mode must be direct|sql|tool")

    model = str(payload.get("model") or "local-small").strip()
    max_steps = int(payload.get("max_steps") or 4)
    max_rows = int(payload.get("max_rows") or 50)
    max_tokens = int(payload.get("max_tokens") or 350)

    # Load config (also loads secrets/db.env early via takctl.config)
    cfg = load_config()
    db = DB(cfg)

    # LLM URL: prefer runtime env override, else cfg.llm_url
    llm_url = (os.environ.get("TAKS_LLM_URL") or cfg.llm_url or "http://127.0.0.1:8090").strip()
    s = llm_status(None)

    steps: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = []

    if mode == "direct":
        # direct: no protocol enforcement, just return raw text
        text_prompt = f"{SYSTEM_PROMPT}\n\nUSER:\n{prompt}\n\nReturn ONLY JSON? No. In direct mode, you may answer normally.\n"
        code, text, err = _call_llama_completions(llm_url, model, text_prompt, max_tokens=max_tokens)
        return ChatResult(
            ok=(code == 200 and bool(text)),
            mode=mode,
            llm={"url": llm_url, "model": model, "status": s},
            steps=[{"type": "llm", "http": code, "error": err, "text": text}],
            final={"text": text, "http": code, "error": err},
        ).__dict__

    # sql/tool: enforce the JSON protocol above
    for step_i in range(max_steps):
        tool_prompt = f"{SYSTEM_PROMPT}\n\n" + _tool_state_to_prompt(prompt, history)
        code, text, err = _call_llama_completions(llm_url, model, tool_prompt, max_tokens=max_tokens)

        steps.append({"type": "llm", "step": step_i + 1, "http": code, "error": err, "raw": (text or "")[:2000]})

        if code != 200 or not text:
            return ChatResult(
                ok=False,
                mode=mode,
                llm={"url": llm_url, "model": model, "status": s},
                steps=steps,
                final={"action": "error", "error": f"llm_failed http={code} err={err}"},
            ).__dict__

        try:
            obj = _extract_json_obj(text)
        except Exception as e:
            history.append({"step": step_i + 1, "llm_parse_error": f"{type(e).__name__}: {e}", "raw": (text or "")[:2000]})
            if mode == "sql":
                # sql mode expects clean behavior; fail fast
                return ChatResult(
                    ok=False,
                    mode=mode,
                    llm={"url": llm_url, "model": model, "status": s},
                    steps=steps,
                    final={"action": "error", "error": "llm_output_not_json", "detail": str(e)},
                ).__dict__
            continue

        action = str(obj.get("action") or "").strip().lower()
        if action == "final":
            return ChatResult(
                ok=True,
                mode=mode,
                llm={"url": llm_url, "model": model, "status": s},
                steps=steps,
                final=obj,
            ).__dict__

        if action != "sql":
            history.append({"step": step_i + 1, "unexpected_action": action, "obj": obj})
            if mode == "sql":
                return ChatResult(
                    ok=False,
                    mode=mode,
                    llm={"url": llm_url, "model": model, "status": s},
                    steps=steps,
                    final={"action": "error", "error": f"unexpected_action {action}", "obj": obj},
                ).__dict__
            continue

        sql = str(obj.get("sql") or "")
        note = str(obj.get("note") or "")
        try:
            sql2 = _sanitize_sql(sql)
        except Exception as e:
            history.append({"step": step_i + 1, "action": "sql", "note": note, "sql_rejected": str(e), "sql": sql})
            if mode == "sql":
                return ChatResult(
                    ok=False,
                    mode=mode,
                    llm={"url": llm_url, "model": model, "status": s},
                    steps=steps,
                    final={"action": "error", "error": "sql_rejected", "detail": str(e)},
                ).__dict__
            continue

        # Execute SQL via python DB helper (psycopg2 when cfg.db_mode=psycopg2)
        try:
            rows = db.fetchall(sql2, ())
            rows_json = _rows_to_json(rows, max_rows=max_rows)
            history.append(
                {
                    "step": step_i + 1,
                    "action": "sql",
                    "note": note,
                    "sql": sql2,
                    "result": {"rows": rows_json, "row_count": len(rows)},
                }
            )
        except Exception as e:
            history.append(
                {
                    "step": step_i + 1,
                    "action": "sql",
                    "note": note,
                    "sql": sql2,
                    "error": f"{type(e).__name__}: {e}",
                }
            )
            if mode == "sql":
                return ChatResult(
                    ok=False,
                    mode=mode,
                    llm={"url": llm_url, "model": model, "status": s},
                    steps=steps,
                    final={"action": "error", "error": "sql_exec_failed", "detail": f"{type(e).__name__}: {e}"},
                ).__dict__

        # sql mode: after exactly one SQL, force a final response next
        if mode == "sql":
            # one more step to request final
            continue

    # ran out of steps
    return ChatResult(
        ok=False,
        mode=mode,
        llm={"url": llm_url, "model": model, "status": s},
        steps=steps,
        final={"action": "error", "error": "max_steps_exceeded", "history": history[-6:]},
    ).__dict__

