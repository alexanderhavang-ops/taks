from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

_TS_RE = re.compile(r"(?:^|_)(ts|time|timestamp|create_time|created|updated|modified|last_edited|servertime|start|end)(?:$|_)", re.I)
_ID_RE = re.compile(r"(?:^|_)(id|uid|guid|uuid)(?:$|_)", re.I)

def _parse_ts_to_epoch(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        # treat as epoch seconds if plausible
        if v > 1_000_000_000:
            return float(v)
        return None
    s = str(v).strip()
    if not s:
        return None

    # normalize common shapes: "2026-02-08 16:39:54.701000+00:00"
    s2 = s.replace("T", " ").replace("Z", "+00:00").strip()
    s2 = re.sub(r"([+-]\d{2}:\d{2})$", "", s2).strip()  # drop tz suffix for parsing

    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:\s+(\d{2}):(\d{2}):(\d{2}))?", s2)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    hh = int(m.group(4) or 0)
    mm = int(m.group(5) or 0)
    ss = int(m.group(6) or 0)
    try:
        import calendar
        return float(calendar.timegm((y, mo, d, hh, mm, ss, 0, 0, 0)))
    except Exception:
        return None

def _iso_utc(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(epoch)))

def build_ops_brief_universal(
    *,
    phase0_obj: dict[str, Any],
    run_id: str,
    generated_utc: str,
    phase0_ref: str,
    domain_id: str,
    domain_title: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Phase1A: universal facts+evidence extractor (structural; not semantic).
    Returns: (brief, trace)

    Goal:
      - Produce a small, UI-friendly "ops_brief" JSON (facts + evidence)
      - Produce a rich trace showing exactly how we derived it
    """
    trace: dict[str, Any] = {
        "contract": {"name": "taks.ops_brief_trace", "version": 1},
        "ok": True,
        "run_id": run_id,
        "domain": {"id": domain_id, "title": domain_title},
        "generated_utc": generated_utc,
        "inputs": {
            "phase0_ref": phase0_ref,
            "phase0_ok": bool(phase0_obj.get("ok")),
            "phase0_phase": phase0_obj.get("phase"),
            "phase0_query_count": len(list(phase0_obj.get("queries") or [])),
        },
        "queries": [],
        "decisions": {},
        "warnings": [],
    }

    queries: List[dict[str, Any]] = list(phase0_obj.get("queries") or [])

    # Summary signals
    row_counts: dict[str, int] = {}
    all_events: list[dict[str, Any]] = []
    entities: dict[str, dict[str, Any]] = {}

    latest_epoch: Optional[float] = None
    latest_src: Optional[str] = None

    id_counts: dict[tuple[str, str], int] = {}
    id_cols_seen: dict[str, int] = {}
    ts_cols_seen: dict[str, int] = {}

    for q in queries:
        qname = str(q.get("name") or "")
        cols = list(q.get("columns") or [])
        rows = list(q.get("rows") or [])
        row_counts[qname] = int(q.get("row_count") or len(rows) or 0)

        ts_cols = [c for c in cols if isinstance(c, str) and _TS_RE.search(c)]
        id_cols = [c for c in cols if isinstance(c, str) and _ID_RE.search(c)]
        for c in ts_cols:
            ts_cols_seen[c] = ts_cols_seen.get(c, 0) + 1
        for c in id_cols:
            id_cols_seen[c] = id_cols_seen.get(c, 0) + 1

        q_trace = {
            "name": qname,
            "ok": bool(q.get("ok")),
            "row_count": int(q.get("row_count") or 0),
            "col_count": len(cols),
            "ts_cols_detected": ts_cols,
            "id_cols_detected": id_cols,
            "events_extracted": 0,
            "entities_extracted": 0,
        }

        for idx, r in enumerate(rows[:200]):
            if not isinstance(r, dict):
                continue

            # choose first parsable ts among detected ts cols
            ts_epoch = None
            ts_col_used = None
            for c in ts_cols:
                if c in r:
                    ts_epoch = _parse_ts_to_epoch(r.get(c))
                    ts_col_used = c
                    if ts_epoch is not None:
                        break

            # update latest activity
            if ts_epoch is not None:
                if latest_epoch is None or ts_epoch > latest_epoch:
                    latest_epoch = ts_epoch
                    latest_src = f"{qname}.{ts_col_used}"

            # concentration counts for id-ish columns
            for c in id_cols:
                if c not in r:
                    continue
                v = r.get(c)
                if v in (None, ""):
                    continue
                key = (c, str(v))
                id_counts[key] = id_counts.get(key, 0) + 1

            # event extraction if ts present
            if ts_epoch is not None:
                bits = []
                for k in ("mission_id", "id", "mission_name", "name", "username", "type", "change_type"):
                    if k in r and r.get(k) not in (None, ""):
                        bits.append(f"{k}={r.get(k)!r}")
                summary = (", ".join(bits)[:220]) if bits else f"{qname} row"
                all_events.append({
                    "ts": _iso_utc(ts_epoch),
                    "type": "row_observed",
                    "source": qname,
                    "summary": summary,
                    "refs": [{"kind": "phase0_query", "id": qname, "row_index": idx}],
                })
                q_trace["events_extracted"] += 1

            # very light entity labeling (structural only)
            if "mission_id" in r and "mission_name" in r and r.get("mission_id") not in (None, "") and r.get("mission_name") not in (None, ""):
                eid = str(r["mission_id"])
                if eid not in entities:
                    entities[eid] = {
                        "kind": "entity",
                        "id": eid,
                        "labels": {"name": str(r["mission_name"])},
                        "refs": [{"kind": "phase0_query", "id": qname, "row_index": idx}],
                    }
                    q_trace["entities_extracted"] += 1
            elif "id" in r and "name" in r and r.get("id") not in (None, "") and r.get("name") not in (None, ""):
                eid = str(r["id"])
                if eid not in entities:
                    entities[eid] = {
                        "kind": "entity",
                        "id": eid,
                        "labels": {"name": str(r["name"])},
                        "refs": [{"kind": "phase0_query", "id": qname, "row_index": idx}],
                    }
                    q_trace["entities_extracted"] += 1

        trace["queries"].append(q_trace)

    primary_field = None
    primary_value = None
    primary_count = 0
    if id_counts:
        (primary_field, primary_value), primary_count = max(id_counts.items(), key=lambda kv: kv[1])

    now_epoch = time.time()
    age_sec = None
    if latest_epoch is not None:
        age_sec = max(0.0, now_epoch - latest_epoch)

    trace["decisions"] = {
        "latest_activity": {
            "latest_ts": _iso_utc(latest_epoch) if latest_epoch is not None else None,
            "latest_ts_source": latest_src,
            "age_sec": int(age_sec) if age_sec is not None else None,
            "age_days": round((age_sec or 0.0) / 86400.0, 2) if age_sec is not None else None,
        },
        "concentration": {
            "primary_id_field": primary_field,
            "primary_id_value": primary_value,
            "primary_id_count": primary_count,
        },
        "detected_columns": {
            "timestamp_like": sorted(ts_cols_seen.items(), key=lambda kv: (-kv[1], kv[0]))[:25],
            "id_like": sorted(id_cols_seen.items(), key=lambda kv: (-kv[1], kv[0]))[:25],
        },
        "bounds": {"max_events": 25, "max_entities": 10},
    }

    brief: dict[str, Any] = {
        "contract": {"name": "taks.ops_brief", "version": 1},
        "domain": {"id": domain_id, "title": domain_title},
        "run": {"run_id": run_id, "generated_utc": generated_utc, "phase0_ref": phase0_ref},
        "signals": {
            "row_counts": row_counts,
            "activity": trace["decisions"]["latest_activity"],
            "concentration": trace["decisions"]["concentration"],
        },
        "evidence": {
            "entities": list(entities.values())[:10],
            "events": sorted(all_events, key=lambda e: e.get("ts") or "")[-25:],
        },
        "bounds": {"max_events": 25, "max_entities": 10},
    }

    return brief, trace
