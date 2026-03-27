from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/llm", tags=["llm"])

USAGE_LOG = Path("/opt/tak/tools/takctl/state/llm_usage.jsonl")


def _safe_int(v: Any) -> int:
    try:
        return int(v)
    except Exception:
        return 0


def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def _month_from_row(o: Dict[str, Any]) -> str:
    for k in ("ts_utc", "started_at"):
        s = _safe_str(o.get(k)).strip()
        if len(s) >= 7 and s[4] == "-":
            return s[:7]
    return ""


def _load_rows() -> List[Dict[str, Any]]:
    if not USAGE_LOG.exists():
        return []

    out: List[Dict[str, Any]] = []
    for line in USAGE_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        if not isinstance(o, dict):
            continue
        month = _month_from_row(o)
        if not month:
            continue
        o["_month"] = month
        out.append(o)
    return out


@router.get("/usage")
async def get_llm_usage(month: str | None = Query(default=None)) -> Dict[str, Any]:
    rows = _load_rows()
    months = sorted({str(r.get("_month") or "") for r in rows if r.get("_month")}, reverse=True)

    selected = (month or "").strip()
    if not selected:
        selected = months[0] if months else ""
    if selected and selected not in months:
        selected = months[0] if months else ""

    chosen = [r for r in rows if not selected or r.get("_month") == selected]

    agg: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "purpose": "",
        "calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "errors": 0,
        "avg_input_tokens": 0,
        "avg_output_tokens": 0,
        "avg_total_tokens": 0,
        "last_ts_utc": "",
    })

    totals = {
        "calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "errors": 0,
    }

    for r in chosen:
        purpose = _safe_str(r.get("purpose")).strip() or "(unlabeled)"
        a = agg[purpose]
        a["purpose"] = purpose
        a["calls"] += 1
        a["input_tokens"] += _safe_int(r.get("input_tokens"))
        a["output_tokens"] += _safe_int(r.get("output_tokens"))
        a["total_tokens"] += _safe_int(r.get("total_tokens"))
        if not bool(r.get("ok", False)):
            a["errors"] += 1

        ts = _safe_str(r.get("ts_utc") or r.get("started_at"))
        if ts and (not a["last_ts_utc"] or ts > a["last_ts_utc"]):
            a["last_ts_utc"] = ts

        totals["calls"] += 1
        totals["input_tokens"] += _safe_int(r.get("input_tokens"))
        totals["output_tokens"] += _safe_int(r.get("output_tokens"))
        totals["total_tokens"] += _safe_int(r.get("total_tokens"))
        if not bool(r.get("ok", False)):
            totals["errors"] += 1

    out_rows: List[Dict[str, Any]] = []
    for purpose, a in agg.items():
        calls = max(1, _safe_int(a["calls"]))
        a["avg_input_tokens"] = int(round(a["input_tokens"] / calls))
        a["avg_output_tokens"] = int(round(a["output_tokens"] / calls))
        a["avg_total_tokens"] = int(round(a["total_tokens"] / calls))
        out_rows.append(a)

    out_rows.sort(key=lambda x: (-_safe_int(x["total_tokens"]), str(x["purpose"])))

    return {
        "ok": True,
        "log_path": str(USAGE_LOG),
        "months": months,
        "selected_month": selected,
        "totals": totals,
        "rows": out_rows,
    }
