from __future__ import annotations

import json
import hashlib
from dataclasses import asdict, is_dataclass
from typing import Any, Optional

from takctl.services.llm import llm_status
from takctl.services.llm_http import http_post_json
from takctl.services.llm_extract import extract_json_from_text

from takctl.services.llm_tools.db_query import run_readonly_query, tool_spec


# -----------------------------------------------------------------------------
# Planner protocol (LLM-visible)
# -----------------------------------------------------------------------------
#
# The model must output ONLY JSON (no prose). Two valid shapes:
#
# 1) Tool call:
#    {
#      "type": "tool",
#      "name": "db.query",
#      "args": { "sql": "SELECT ...", "params": [], "statement_timeout_ms": 3000, "max_rows": 200 }
#    }
#
# 2) Final render plan (UI-agnostic):
#    {
#      "type": "final",
#      "plan": {
#        "schema_version": "taks.renderplan.v1",
#        "view": "tactical-operations",
#        "meta": {...},
#        "datasets": {...},
#        "blocks": [...]
#      }
#    }
#
# Any other output is considered invalid and triggers fallback.
# -----------------------------------------------------------------------------


def _json_default(o: Any) -> Any:
    if is_dataclass(o):
        return asdict(o)
    return str(o)


def _safe_json(obj: Any) -> str:
    return json.dumps(obj, default=_json_default, ensure_ascii=False, indent=2, sort_keys=True)


def _renderplan_stub(view: str, reason: str, trace: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "taks.renderplan.v1",
        "view": view,
        "meta": {
            "mode": "heuristic",
            "fallback_reason": reason,
        },
        "datasets": {},
        "blocks": [
            {"type": "header", "title": f"{view}"},
            {
                "type": "markdown",
                "title": "LLM planner fallback",
                "body": reason,
            },
            {
                "type": "json",
                "title": "Trace",
                "body": trace,
            },
        ],
    }


def _build_prompt(view: str, snapshot: dict[str, Any], trace: list[dict[str, Any]]) -> str:
    """
    Keep this deterministic and auditable: snapshot + tool spec + trace.
    No hidden reasoning required.
    """
    protocol = {
        "output_rules": [
            "Return ONLY JSON. No prose, no markdown fences.",
            "Valid outputs are either a tool call object or a final plan object.",
            "If you need DB info, emit a db.query tool call.",
            "Keep queries read-only (SELECT/WITH). Prefer information_schema/pg_catalog discovery first.",
            "Never ask for credentials. Assume DB tool already has access.",
        ],
        "tool": tool_spec(),
        "tool_call_shape": {
            "type": "tool",
            "name": "db.query",
            "args": {
                "sql": "SELECT ...",
                "params": [],
                "statement_timeout_ms": 3000,
                "max_rows": 200,
            },
        },
        "final_shape": {
            "type": "final",
            "plan": {
                "schema_version": "taks.renderplan.v1",
                "view": view,
                "meta": {},
                "datasets": {},
                "blocks": [],
            },
        },
    }

    payload = {
        "view": view,
        "snapshot": snapshot,
        "protocol": protocol,
        "trace": trace[-6:],  # keep context bounded
    }

    return _safe_json(payload)


def _call_llm_completions(llm_url: str, model: str, prompt: str, max_tokens: int) -> tuple[int, Optional[dict[str, Any]], Optional[str], str]:
    """
    llama.cpp exposes OpenAI-like /v1/completions. We expect:
      { choices: [ { text: "..." } ], ... }
    Returns (http_code, json_body, err, raw_text)
    """
    req = {
        "model": model,
        "prompt": prompt,
        "max_tokens": int(max_tokens),
        "temperature": 0.0,
        "stream": False,
    }
    code, body, err = http_post_json(f"{llm_url.rstrip('/')}/v1/completions", req, timeout_sec=180.0)

    raw_text = ""
    if code == 200 and isinstance(body, dict):
        try:
            raw_text = str(((body.get("choices") or [{}])[0] or {}).get("text") or "")
        except Exception:
            raw_text = ""
    return code, body, err, raw_text


def plan_with_tools(
    *,
    view: str,
    snapshot: dict[str, Any],
    model: str = "local-small",
    max_iters: int = 6,
    max_tokens: int = 450,
) -> dict[str, Any]:
    """
    Tool-iterative planner:
      - LLM proposes db.query calls
      - We execute them (bounded)
      - Feed results back
      - Repeat until LLM returns a final RenderPlan
    """
    trace: list[dict[str, Any]] = []

    status = llm_status(None)
    llm_url = status.get("url") or "http://127.0.0.1:8090"
    ok = bool((status.get("health") or {}).get("ok"))
    if not ok:
        return _renderplan_stub(view, f"llm_unreachable: {status.get('health')}", trace)

    for i in range(int(max_iters)):
        prompt = _build_prompt(view=view, snapshot=snapshot, trace=trace)

        code, body, err, raw_text = _call_llm_completions(llm_url, model, prompt, max_tokens=max_tokens)

        # Record bounded introspection for UI/debug (safe size)
        prompt_head = prompt[:2400]
        prompt_tail = prompt[-800:] if len(prompt) > 800 else ""
        prompt_sha = hashlib.sha256(prompt.encode("utf-8", "ignore")).hexdigest()[:16]

        trace.append(
            {
                "step": i,
                "llm_http": code,
                "llm_err": err,
                "llm_url": llm_url,
                "llm_model": model,
                "llm_max_tokens": int(max_tokens),
                "llm_temperature": 0.0,
                "prompt_sha16": prompt_sha,
                "prompt_head": prompt_head,
                "prompt_tail": prompt_tail,
                "llm_raw_head": raw_text[:1200],
                "llm_body_head": (str(body)[:1200] if isinstance(body, dict) else str(body)[:1200]),
            }
        )

        if code != 200:
            return _renderplan_stub(view, f"llm_http_error: code={code} err={err}", trace)

        extracted, extract_err, candidate = extract_json_from_text(raw_text)
        if extracted is None or not isinstance(extracted, dict):
            trace.append(
                {
                    "step": i,
                    "parse_error": extract_err,
                    "candidate_head": (candidate or "")[:600],
                }
            )
            return _renderplan_stub(view, f"llm_output_not_json: {extract_err}", trace)

        typ = (extracted.get("type") or "").strip()

        # --- Final ---
        if typ == "final":
            plan = extracted.get("plan")
            if isinstance(plan, dict) and plan.get("schema_version") == "taks.renderplan.v1":
                # Add minimal meta for auditability
                meta = dict(plan.get("meta") or {})
                meta.setdefault("mode", "llm-tools")
                meta.setdefault("model", model)
                meta.setdefault("llm_url", llm_url)
                plan["meta"] = meta
                try:
                    return validate_renderplan(plan)
                except RenderPlanError as e:
                    trace.append({"step": i, "final_validation_error": str(e), "final_obj": extracted})
                    return _renderplan_stub(view, f"llm_final_invalid: {e}", trace)

            trace.append({"step": i, "final_invalid": True, "final_obj": extracted})
            return _renderplan_stub(view, "llm_final_invalid", trace)

        # --- Tool call ---
        if typ == "tool":
            name = (extracted.get("name") or "").strip()
            args = extracted.get("args") or {}
            if name != "db.query" or not isinstance(args, dict):
                trace.append({"step": i, "tool_invalid": True, "tool_obj": extracted})
                return _renderplan_stub(view, "llm_tool_invalid", trace)

            sql = str(args.get("sql") or "")
            params = args.get("params") or []
            if not isinstance(params, list):
                params = []

            stm = int(args.get("statement_timeout_ms") or 3000)
            mrows = int(args.get("max_rows") or 200)

            res = run_readonly_query(
                sql,
                tuple(params),
                statement_timeout_ms=stm,
                max_rows=mrows,
            )
            trace.append(
                {
                    "step": i,
                    "tool": "db.query",
                    "ok": bool(res.ok),
                    "sql": res.sql,
                    "elapsed_ms": res.elapsed_ms,
                    "rowcount": res.rowcount,
                    "columns": res.columns,
                    "error": res.error,
                    # keep rows bounded in trace; they are already limited + truncated
                    "rows": res.rows,
                }
            )

            # continue loop regardless; LLM can react to error/empty
            continue

        # Unknown output type
        trace.append({"step": i, "unknown_type": typ, "obj": extracted})
        return _renderplan_stub(view, f"llm_unknown_type: {typ}", trace)

    return _renderplan_stub(view, "max_iters_exceeded", trace)

