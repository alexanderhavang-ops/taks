from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
import traceback
from pathlib import Path
from takctl.config import load_config
from typing import Any, Dict, List, Tuple

from takctl.services.llm2.domain_config import (
    discover_enabled_domains,
    load_domain_config,
    phase_enabled,
    phase_input,
    phase_output_schema,
    upstream_domains,
)
from takctl.services.llm2.llm_client import LlmClient
from takctl.services.llm2.paths import latest_root, runs_root
from takctl.config_store import load_runtime_config_view
from takctl.services.llm2.store import write_json

REQ_KEYS = ("important", "newest", "details")
PROFILE_ORDER = ("compact", "standard", "full")


def _extract_first_json_object(text: str) -> str:
    if not text:
        raise ValueError("empty_text")

    s = text
    i0 = s.find("{")
    if i0 < 0:
        raise ValueError("no_json_object_start")

    s = s[i0:]

    depth = 0
    in_str = False
    esc = False
    end_idx = None

    for idx, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                end_idx = idx + 1
                break
            continue

    if end_idx is None:
        if in_str:
            raise ValueError("truncated_inside_string")

        if depth <= 0:
            j = s.rfind("}")
            if j >= 0:
                return s[: j + 1]
            raise ValueError("no_closing_brace_found")

        return s + ("}" * depth)

    return s[:end_idx]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _read_json(p: Path) -> Any:
    return json.loads(_read_text(p))


def _sha256_text(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8", errors="replace")).hexdigest()


def _sanitize_jsonish_text(raw: str) -> str:
    t = (raw or "").strip()
    if not t:
        return t

    for _ in range(10):
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

    lines = t.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and lines[-1].strip() == "```":
        lines.pop()
    t = "\n".join(lines).strip()

    if not t:
        return t

    i_obj = t.find("{")
    i_arr = t.find("[")
    starts = [i for i in (i_obj, i_arr) if i != -1]
    if not starts:
        return t
    start = min(starts)

    end = max(t.rfind("}"), t.rfind("]"))
    if end == -1 or end < start:
        return t[start:].strip()

    return t[start : end + 1].strip()


def _phase1_gate(latest_dom_dir: Path) -> Tuple[bool, str]:
    p_trace = latest_dom_dir / "phase1" / "trace.json"
    p_latest = latest_dom_dir / "phase1" / "latest.json"

    if not p_trace.exists():
        return False, "phase1_trace_missing"
    if not p_latest.exists():
        return False, "phase1_latest_json_missing"

    try:
        trace = _read_json(p_trace)
    except Exception:
        return False, "phase1_trace_invalid_json"

    if not trace.get("ok", False):
        return False, f"phase1_failed:{trace.get('error')}"

    return True, "ok"


def _phase2_evidence_profile() -> str:
    cfg = load_config()
    return (cfg.llm_phase2_evidence_profile or "compact").strip().lower()


def _select_profile_payload_from_phase1(obj: Any) -> tuple[str | None, Any]:
    if not isinstance(obj, dict):
        return None, None

    wanted = _phase2_evidence_profile()
    queries = obj.get("queries")
    if not isinstance(queries, list):
        return None, None

    for q in queries:
        if not isinstance(q, dict):
            continue
        evidence = q.get("evidence")
        if not isinstance(evidence, dict):
            continue

        if wanted in evidence:
            return wanted, evidence.get(wanted)

        for name in PROFILE_ORDER:
            if name in evidence:
                return name, evidence.get(name)

    return None, None


def _phase1_evidence_obj(latest_dom_dir: Path) -> Dict[str, Any]:
    p_latest = latest_dom_dir / "phase1" / "latest.json"
    if not p_latest.exists():
        return {}

    try:
        obj = _read_json(p_latest)
    except Exception:
        raw = _read_text(p_latest).strip()
        return {"raw_phase1_evidence": raw} if raw else {}

    chosen_profile, chosen_payload = _select_profile_payload_from_phase1(obj)
    if chosen_payload is not None:
        if isinstance(chosen_payload, dict):
            return chosen_payload
        return {"profile": chosen_profile or "", "payload": chosen_payload}

    if isinstance(obj, dict):
        return obj
    return {"raw_phase1_evidence": str(obj)}


def _runtime_language() -> str:
    try:
        cfg = load_runtime_config_view()
        lang = str(cfg.get("language", "sv")).strip().lower()
        return lang or "sv"
    except Exception:
        return "sv"


def _load_prompt(infra_dir: Path, dom: str) -> Tuple[str, str]:
    base = infra_dir / "domains" / dom / "prompts" / "phase2"
    lang = _runtime_language()

    candidates = [
        (base / lang / "system.txt", base / lang / "user.txt"),
        (base / "en" / "system.txt", base / "en" / "user.txt"),
        (base / "system.txt", base / "user.txt"),
    ]

    for sys_p, usr_p in candidates:
        system_txt = _read_text(sys_p).strip()
        user_txt = _read_text(usr_p).strip()
        if system_txt and user_txt:
            return system_txt, user_txt

    raise RuntimeError(f"missing prompt files for domain={dom} lang={lang}: {candidates}")


def _build_prompt(system_txt: str, user_txt: str, evidence_json: str) -> str:
    parts: List[str] = [
        system_txt.strip(),
        "",
        user_txt.strip(),
        "",
        "## INPUT",
        evidence_json.strip(),
        "",
    ]
    return "\n".join(parts).strip() + "\n"


def _validate_standard_summary_obj(obj: Any) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        raise RuntimeError("not_a_json_object")

    for k in REQ_KEYS:
        if k not in obj:
            raise RuntimeError(f"missing_key:{k}")

    for k in REQ_KEYS:
        if not isinstance(obj.get(k), str):
            obj[k] = "" if obj.get(k) is None else str(obj.get(k))

    return obj


def _validate_timeline_phase2_v1_obj(obj: Any) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        raise RuntimeError("timeline_phase2_not_object")

    if str(obj.get("schema") or "").strip() != "timeline.phase2.v1":
        raise RuntimeError("timeline_phase2_schema_mismatch")

    obj["domain"] = str(obj.get("domain") or "timeline").strip() or "timeline"
    obj["generated_utc"] = "" if obj.get("generated_utc") is None else str(obj.get("generated_utc"))

    root_now = obj.get("now_utc")
    root_left = obj.get("left_utc")
    root_right = obj.get("right_utc")
    root_past = obj.get("past_hours")
    root_future = obj.get("future_hours")

    window = obj.get("window")
    if not isinstance(window, dict):
        window = {}
        obj["window"] = window

    now_utc = window.get("now_utc", root_now)
    left_utc = window.get("left_utc", root_left)
    right_utc = window.get("right_utc", root_right)
    past_hours = window.get("past_hours", root_past if root_past is not None else 24)
    future_hours = window.get("future_hours", root_future if root_future is not None else 24)

    window["now_utc"] = "" if now_utc is None else str(now_utc)
    window["left_utc"] = "" if left_utc is None else str(left_utc)
    window["right_utc"] = "" if right_utc is None else str(right_utc)

    try:
        window["past_hours"] = int(past_hours)
    except Exception:
        window["past_hours"] = 24

    try:
        window["future_hours"] = int(future_hours)
    except Exception:
        window["future_hours"] = 24

    window["timezone"] = str(window.get("timezone") or "UTC")

    headline = obj.get("headline")
    if not isinstance(headline, dict):
        raise RuntimeError("missing_or_invalid_headline")

    for k in ("important", "newest", "next"):
        if k not in headline:
            headline[k] = ""
        if not isinstance(headline.get(k), str):
            headline[k] = "" if headline.get(k) is None else str(headline.get(k))

    lanes = obj.get("lanes")
    if not isinstance(lanes, list):
        raise RuntimeError("missing_or_invalid_lanes")

    norm_lanes = []
    for lane_idx, lane in enumerate(lanes):
        if not isinstance(lane, dict):
            continue

        lane_id = str(lane.get("id") or "").strip()
        if not lane_id:
            lane_id = f"lane_{lane_idx}"

        lane_title = lane.get("title")
        if lane_title is None:
            lane_title = lane.get("label")
        if lane_title is None:
            lane_title = lane_id

        items = lane.get("items")
        if not isinstance(items, list):
            items = []

        norm_items = []
        for item_idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue

            kind = str(item.get("kind") or item.get("type") or "").strip().lower()
            if kind not in ("point", "interval"):
                if item.get("start_utc") is not None or item.get("end_utc") is not None or item.get("t_start") is not None or item.get("t_end") is not None:
                    kind = "interval"
                elif item.get("time_utc") is not None or item.get("t") is not None:
                    kind = "point"
                else:
                    raise RuntimeError(f"invalid_item_kind:{kind or 'missing'}")

            item_id = str(item.get("id") or "").strip() or f"{lane_id}_{kind}_{item_idx+1}"
            label = item.get("label")
            if label is None:
                label = item.get("title")
            label = "" if label is None else str(label)

            summary = item.get("summary")
            if summary is None:
                summary = item.get("note")
            if summary is None:
                summary = item.get("details")
            summary = "" if summary is None else str(summary)

            status = "" if item.get("status") is None else str(item.get("status"))
            priority = "" if item.get("priority") is None else str(item.get("priority"))

            source_domain = item.get("source_domain")
            if source_domain is None:
                source_domain = lane_id
            source_domain = "" if source_domain is None else str(source_domain)

            raw_refs = item.get("source_refs")
            norm_refs = []
            if raw_refs is None:
                norm_refs = []
            elif isinstance(raw_refs, list):
                for ref in raw_refs:
                    if isinstance(ref, dict):
                        norm_refs.append({
                            "domain": "" if ref.get("domain") is None else str(ref.get("domain")),
                            "item_id": "" if ref.get("item_id") is None else str(ref.get("item_id")),
                        })
                    else:
                        norm_refs.append({
                            "domain": source_domain,
                            "item_id": "" if ref is None else str(ref),
                        })
            else:
                norm_refs = [{
                    "domain": source_domain,
                    "item_id": str(raw_refs),
                }]

            out = {
                "id": item_id,
                "kind": kind,
                "label": label,
                "summary": summary,
                "status": status,
                "priority": priority,
                "source_domain": source_domain,
                "source_refs": norm_refs,
            }

            if kind == "point":
                time_utc = item.get("time_utc")
                if time_utc is None:
                    time_utc = item.get("t")
                if time_utc is None:
                    time_utc = item.get("timestamp")
                out["time_utc"] = "" if time_utc is None else str(time_utc)
                out["unit"] = "" if item.get("unit") is None else str(item.get("unit"))
                out["marker"] = "" if item.get("marker") is None else str(item.get("marker"))
            else:
                start_utc = item.get("start_utc")
                if start_utc is None:
                    start_utc = item.get("t_start")
                if start_utc is None:
                    start_utc = item.get("start")

                end_utc = item.get("end_utc")
                if end_utc is None:
                    end_utc = item.get("t_end")
                if end_utc is None:
                    end_utc = item.get("end")

                out["start_utc"] = "" if start_utc is None else str(start_utc)
                out["end_utc"] = "" if end_utc is None else str(end_utc)
                out["band_style"] = "" if item.get("band_style") is None else str(item.get("band_style"))

            norm_items.append(out)

        norm_lanes.append({
            "id": lane_id,
            "title": str(lane_title),
            "items": norm_items,
        })

    obj["lanes"] = norm_lanes

    render_hints = obj.get("render_hints")
    if render_hints is None:
        render_hints = {}
        obj["render_hints"] = render_hints
    elif not isinstance(render_hints, dict):
        render_hints = {}
        obj["render_hints"] = render_hints

    dense = render_hints.get("dense_clusters")
    norm_dense = []
    if isinstance(dense, list):
        for cluster in dense:
            if isinstance(cluster, dict):
                norm_dense.append({
                    "lane_id": "" if cluster.get("lane_id", cluster.get("lane")) is None else str(cluster.get("lane_id", cluster.get("lane"))),
                    "start_utc": "" if cluster.get("start_utc", cluster.get("t_start")) is None else str(cluster.get("start_utc", cluster.get("t_start"))),
                    "end_utc": "" if cluster.get("end_utc", cluster.get("t_end")) is None else str(cluster.get("end_utc", cluster.get("t_end"))),
                    "note": "" if cluster.get("note") is None else str(cluster.get("note")),
                })
            else:
                norm_dense.append({
                    "lane_id": "",
                    "start_utc": "" if cluster is None else str(cluster),
                    "end_utc": "" if cluster is None else str(cluster),
                    "note": "",
                })
    render_hints["dense_clusters"] = norm_dense

    return obj



def _validate_obj_for_schema(obj: Any, schema_name: str) -> Dict[str, Any]:
    schema_name = str(schema_name or "").strip()
    if schema_name == "standard.summary.v1":
        return _validate_standard_summary_obj(obj)
    if schema_name == "timeline.phase2.v1":
        return _validate_timeline_phase2_v1_obj(obj)
    raise RuntimeError(f"unsupported_output_schema:{schema_name}")


def _parse_utc_ts(value: Any) -> datetime | None:
    s = str(value or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _fmt_utc_ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _timeline_window_bounds(obj: Dict[str, Any]) -> tuple[datetime | None, datetime | None, datetime | None]:
    window = obj.get("window")
    if not isinstance(window, dict):
        return None, None, None

    now_dt = _parse_utc_ts(window.get("now_utc"))
    if now_dt is None:
        return None, None, None

    try:
        past_hours = int(window.get("past_hours", 24))
    except Exception:
        past_hours = 24

    try:
        future_hours = int(window.get("future_hours", 24))
    except Exception:
        future_hours = 24

    left_dt = _parse_utc_ts(window.get("left_utc")) or (now_dt - timedelta(hours=past_hours))
    right_dt = _parse_utc_ts(window.get("right_utc")) or (now_dt + timedelta(hours=future_hours))

    if left_dt > right_dt:
        left_dt, right_dt = right_dt, left_dt

    window["now_utc"] = _fmt_utc_ts(now_dt)
    window["left_utc"] = _fmt_utc_ts(left_dt)
    window["right_utc"] = _fmt_utc_ts(right_dt)
    window["past_hours"] = past_hours
    window["future_hours"] = future_hours
    window["timezone"] = "UTC"

    return now_dt, left_dt, right_dt


def _prune_timeline_phase2_obj(obj: Dict[str, Any]) -> Dict[str, Any]:
    _now_dt, left_dt, right_dt = _timeline_window_bounds(obj)
    if left_dt is None or right_dt is None:
        return obj

    lanes = obj.get("lanes")
    if isinstance(lanes, list):
        for lane in lanes:
            if not isinstance(lane, dict):
                continue
            items = lane.get("items")
            if not isinstance(items, list):
                lane["items"] = []
                continue

            kept = []
            for item in items:
                if not isinstance(item, dict):
                    continue

                kind = str(item.get("kind") or "").strip()
                if kind == "point":
                    t = _parse_utc_ts(item.get("time_utc"))
                    if t is None:
                        kept.append(item)
                        continue
                    if left_dt <= t <= right_dt:
                        item["time_utc"] = _fmt_utc_ts(t)
                        kept.append(item)
                    continue

                if kind == "interval":
                    start_dt = _parse_utc_ts(item.get("start_utc"))
                    end_dt = _parse_utc_ts(item.get("end_utc"))

                    eff_start = start_dt or left_dt
                    eff_end = end_dt or right_dt

                    if eff_end < left_dt or eff_start > right_dt:
                        continue

                    clamped_start = max(eff_start, left_dt)
                    clamped_end = min(eff_end, right_dt)

                    item["start_utc"] = _fmt_utc_ts(clamped_start)
                    item["end_utc"] = _fmt_utc_ts(clamped_end)
                    kept.append(item)
                    continue

                kept.append(item)

            lane["items"] = kept

    render_hints = obj.get("render_hints")
    if isinstance(render_hints, dict):
        dense = render_hints.get("dense_clusters")
        if isinstance(dense, list):
            kept_dense = []
            for cluster in dense:
                if not isinstance(cluster, dict):
                    continue
                start_dt = _parse_utc_ts(cluster.get("start_utc"))
                end_dt = _parse_utc_ts(cluster.get("end_utc"))
                eff_start = start_dt or left_dt
                eff_end = end_dt or right_dt
                if eff_end < left_dt or eff_start > right_dt:
                    continue
                cluster["start_utc"] = _fmt_utc_ts(max(eff_start, left_dt))
                cluster["end_utc"] = _fmt_utc_ts(min(eff_end, right_dt))
                kept_dense.append(cluster)
            render_hints["dense_clusters"] = kept_dense
        else:
            render_hints["dense_clusters"] = []

    total_items = 0
    if isinstance(lanes, list):
        for lane in lanes:
            if isinstance(lane, dict) and isinstance(lane.get("items"), list):
                total_items += len(lane["items"])

    if total_items == 0:
        obj["headline"] = {
            "important": "No timeline findings within the 24-hour past/future window.",
            "newest": "",
            "next": "",
        }

    return obj


def _pick_sentences(text: str, limit: int) -> list[str]:
    s = re.sub(r"\s+", " ", (text or "").strip())
    if not s:
        return []
    parts = re.split(r"(?<=[\.\!\?])\s+", s)
    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        out.append(p)
        if len(out) >= limit:
            break
    return out


def _strip_json_noise(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return ""
    s = re.sub(r"```(?:json)?", "", s, flags=re.IGNORECASE).strip()
    s = re.sub(r'^\s*[\{\[]', "", s)
    s = re.sub(r'[\}\]]\s*$', "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _empty_obj_for_schema(schema_name: str, *, dom: str, message: str) -> Dict[str, Any]:
    if schema_name == "timeline.phase2.v1":
        return {
            "schema": "timeline.phase2.v1",
            "domain": "timeline",
            "generated_utc": "",
            "window": {
                "now_utc": "",
                "past_hours": 24,
                "future_hours": 24,
                "left_utc": "",
                "right_utc": "",
                "timezone": "UTC",
            },
            "headline": {
                "important": message,
                "newest": "",
                "next": "",
            },
            "lanes": [
                {"id": "enemy", "title": "Enemy", "items": []},
                {"id": "friendly", "title": "Friendly / Presence", "items": []},
                {"id": "orders", "title": "Orders / Chatter", "items": []},
                {"id": "missions", "title": "Missions", "items": []},
                {"id": "weather", "title": "Weather", "items": []},
            ],
            "render_hints": {"dense_clusters": []},
        }

    return {
        "important": message,
        "newest": "",
        "details": "",
    }


def _summary_fallback_from_sentences(sentences: list[str], raw_text: str, dom: str) -> Dict[str, Any]:
    important = sentences[0] if sentences else f"{dom} findings unavailable."
    newest = sentences[1] if len(sentences) > 1 else ""
    details = " ".join(sentences[2:6]) if len(sentences) > 2 else raw_text[:600]

    if not details:
        details = important

    return {
        "important": important[:400].strip(),
        "newest": newest[:400].strip(),
        "details": details[:1200].strip(),
    }


def _timeline_fallback_from_sentences(sentences: list[str]) -> Dict[str, Any]:
    headline_important = sentences[0] if sentences else "Timeline findings unavailable."
    headline_newest = sentences[1] if len(sentences) > 1 else ""
    headline_next = sentences[2] if len(sentences) > 2 else ""

    return {
        "schema": "timeline.phase2.v1",
        "domain": "timeline",
        "generated_utc": "",
        "window": {
            "now_utc": "",
            "past_hours": 24,
            "future_hours": 24,
            "left_utc": "",
            "right_utc": "",
            "timezone": "UTC",
        },
        "headline": {
            "important": headline_important[:400].strip(),
            "newest": headline_newest[:400].strip(),
            "next": headline_next[:400].strip(),
        },
        "lanes": [
            {"id": "enemy", "title": "Enemy", "items": []},
            {"id": "friendly", "title": "Friendly / Presence", "items": []},
            {"id": "orders", "title": "Orders / Chatter", "items": []},
            {"id": "missions", "title": "Missions", "items": []},
            {"id": "weather", "title": "Weather", "items": []},
        ],
        "render_hints": {"dense_clusters": []},
    }


def _deterministic_fallback_from_text(raw_text: str, dom: str, schema_name: str) -> Dict[str, Any]:
    s = _strip_json_noise(raw_text)
    sentences = _pick_sentences(s, 8)

    if schema_name == "standard.summary.v1":
        return _summary_fallback_from_sentences(sentences, s, dom)

    if schema_name == "timeline.phase2.v1":
        return _empty_obj_for_schema(
            schema_name,
            dom=dom,
            message="Timeline parse failed. See phase2 trace raw/cleaned response.",
        )

    raise RuntimeError(f"unsupported_output_schema:{schema_name}")


def _gather_upstream_phase2_findings(*, latest_dir: Path, upstream: list[str]) -> Dict[str, Any]:
    domains: Dict[str, Any] = {}
    if not latest_dir.exists():
        return {"ok": False, "error": "latest_root_missing", "domains": domains}

    for dom in upstream:
        dom_dir = latest_dir / dom
        p_find = dom_dir / "phase2" / "findings.json"
        entry: Dict[str, Any] = {"ok": False}

        if not p_find.exists():
            entry["error"] = "phase2_findings_missing"
            domains[dom] = entry
            continue

        try:
            fo = _read_json(p_find)
        except Exception as e:
            entry["error"] = f"phase2_findings_invalid_json:{type(e).__name__}: {e}"
            domains[dom] = entry
            continue

        if not isinstance(fo, dict):
            entry["error"] = "phase2_findings_not_object"
            domains[dom] = entry
            continue

        entry["ok"] = True
        entry["findings"] = fo
        domains[dom] = entry

    return {"ok": True, "domains": domains}


def _phase2_input_payload(*, infra_dir: Path, latest_dir: Path, dom: str) -> Dict[str, Any]:
    cfg = load_domain_config(infra_dir, dom)
    p2_input = phase_input(cfg, "phase2")

    if p2_input == "phase1_evidence":
        latest_dom_dir = latest_dir / dom
        return _phase1_evidence_obj(latest_dom_dir)

    if p2_input == "upstream_phase2_findings":
        upstream = upstream_domains(cfg)
        return _gather_upstream_phase2_findings(latest_dir=latest_dir, upstream=upstream)

    raise RuntimeError(f"unsupported phase2 input for {dom}: {p2_input!r}")


def _phase2_domains_in_order(infra_dir: Path) -> List[str]:
    domains = discover_enabled_domains(infra_dir)

    leaves: List[str] = []
    synthesizers: List[str] = []

    for dom in domains:
        cfg = load_domain_config(infra_dir, dom)
        p2_input = phase_input(cfg, "phase2")
        if p2_input == "upstream_phase2_findings":
            synthesizers.append(dom)
        else:
            leaves.append(dom)

    return leaves + synthesizers


def run_phase2(*, run_id: str, domain: str | None = None) -> Dict[str, Any]:
    started = _now_iso()
    t0 = time.time()

    cfg0 = load_config()
    infra_dir = Path(cfg0.llm_infra_dir)
    client = LlmClient()

    n_predict = int(cfg0.llm_n_predict)
    temperature = float(cfg0.llm_temperature)

    domains = _phase2_domains_in_order(infra_dir)
    dom = (domain or "").strip()
    if dom and dom.lower() != "all":
        domains = [d for d in domains if d == dom]

    out: Dict[str, Any] = {
        "ok": True,
        "run_id": run_id,
        "phase": "phase2",
        "started_at": started,
        "provider": getattr(client, "provider", None),
        "model": (client.bedrock_model_id if getattr(client, "provider", "") == "bedrock" else client.model),
        "n_predict": n_predict,
        "temperature": temperature,
        "domains": domains,
        "env_path": getattr(client, "env_path", None),
    }

    any_fail = False

    (runs_root() / run_id).mkdir(parents=True, exist_ok=True)
    latest_root().mkdir(parents=True, exist_ok=True)

    def _run_one_domain(dom: str) -> None:
        nonlocal any_fail

        dom_t0 = time.time()
        dom_started = _now_iso()

        latest_dom_dir = latest_root() / dom
        run_dom_dir = runs_root() / run_id / dom / "phase2"
        run_dom_dir.mkdir(parents=True, exist_ok=True)

        latest_phase2_dir = latest_dom_dir / "phase2"
        latest_phase2_dir.mkdir(parents=True, exist_ok=True)

        req_path = run_dom_dir / "request.json"
        prompt_path = run_dom_dir / "prompt.txt"
        resp_http_path = run_dom_dir / "response.http.json"
        resp_raw_path = run_dom_dir / "response_raw.json"
        resp_text_path = run_dom_dir / "response_text.txt"
        cleaned_path = run_dom_dir / "cleaned_text.txt"
        findings_path = run_dom_dir / "findings.json"

        latest_findings_path = latest_phase2_dir / "findings.json"
        trace_run_path = run_dom_dir / "trace.json"
        trace_latest_path = latest_phase2_dir / "trace.json"

        trace: Dict[str, Any] = {
            "phase": "phase2",
            "domain": dom,
            "run_id": run_id,
            "started_at": dom_started,
            "ok": False,
            "provider": getattr(client, "provider", None),
            "model": (client.bedrock_model_id if getattr(client, "provider", "") == "bedrock" else client.model),
            "temperature": temperature,
            "n_predict": n_predict,
            "phase1_gate": None,
            "phase2_input": "",
            "phase2_output_schema": "",
            "domain_mode": "",
            "phase2_enabled": False,
            "error": None,
            "sent": {},
            "received": {},
            "repair": {},
            "files": {
                "request_path": str(req_path),
                "prompt_path": str(prompt_path),
                "response_http_path": str(resp_http_path),
                "response_raw_path": str(resp_raw_path),
                "response_text_path": str(resp_text_path),
                "cleaned_text_path": str(cleaned_path),
                "findings_path": str(findings_path),
                "latest_findings_path": str(latest_findings_path),
                "trace_path": str(trace_latest_path),
                "trace_run_path": str(trace_run_path),
            },
        }

        try:
            cfg = load_domain_config(infra_dir, dom)
            p2_input_kind = phase_input(cfg, "phase2")
            schema_name = phase_output_schema(cfg, "phase2")

            trace["domain_mode"] = str(cfg.get("mode") or "")
            trace["phase2_enabled"] = phase_enabled(cfg, "phase2")
            trace["phase2_input"] = p2_input_kind
            trace["phase2_output_schema"] = schema_name

            if p2_input_kind == "phase1_evidence":
                ok, reason = _phase1_gate(latest_dom_dir)
            else:
                ok, reason = True, f"phase2_input:{p2_input_kind}"

            trace["phase1_gate"] = {"ok": ok, "reason": reason}

            if not ok:
                print(f"\n===== PHASE2 SKIP [{dom}] reason={reason} =====")
                obj = _empty_obj_for_schema(schema_name, dom=dom, message=f"No evidence ({reason}).")
                write_json(findings_path, obj)
                write_json(latest_findings_path, obj)
                trace["ok"] = True
                trace["note"] = "phase2_short_circuit_no_input_evidence"
                return

            evidence_obj = _phase2_input_payload(
                infra_dir=infra_dir,
                latest_dir=latest_root(),
                dom=dom,
            )
            evidence = json.dumps(evidence_obj, ensure_ascii=False, indent=2, sort_keys=True)

            if not evidence.strip() or evidence.strip() == "{}":
                print(f"\n===== PHASE2 SKIP [{dom}] reason=empty_evidence =====")
                obj = _empty_obj_for_schema(schema_name, dom=dom, message="No evidence.")
                write_json(findings_path, obj)
                write_json(latest_findings_path, obj)
                trace["ok"] = True
                trace["note"] = "phase2_short_circuit_empty_evidence"
                return

            system_txt, user_txt = _load_prompt(infra_dir, dom)
            prompt = _build_prompt(system_txt, user_txt, evidence)

            prompt_path.write_text(prompt, encoding="utf-8")

            write_json(req_path, {
                "provider": getattr(client, "provider", None),
                "model": (client.bedrock_model_id if getattr(client, "provider", "") == "bedrock" else client.model),
                "temperature": temperature,
                "max_tokens": n_predict,
                "prompt_sha256": _sha256_text(prompt),
            })

            print(f"\n===== PHASE2 SENT [{dom}] =====")
            print(f"temperature={temperature}")
            print(f"prompt_bytes={len(prompt.encode('utf-8'))} sha256={_sha256_text(prompt)}")
            print("--- prompt_full ---")
            print(prompt)

            trace["sent"] = {
                "prompt_sha256": _sha256_text(prompt),
                "prompt_bytes": len(prompt.encode("utf-8")),
                "prompt_full": prompt,
            }

            r = client.complete_text(
                prompt=prompt,
                temperature=temperature,
                max_tokens=n_predict,
                seed=7,
                purpose=f"phase2:{dom}",
            )
            text = r.get("text") or ""
            resp_text_path.write_text(text, encoding="utf-8")

            write_json(resp_http_path, {
                "provider": r.get("provider"),
                "url": r.get("url"),
                "model": r.get("model"),
                "http_status": r.get("http_status"),
                "body_bytes": r.get("body_bytes"),
                "error": r.get("error"),
            })
            write_json(resp_raw_path, {"text": text})

            print(f"\n===== PHASE2 RECEIVED [{dom}] =====")
            print(f"http_status={r.get('http_status')} bytes={r.get('body_bytes')}")
            print(f"text_bytes={len(text.encode('utf-8'))} text_sha256={_sha256_text(text)}")
            print("--- response_text_raw ---")
            print(text)

            trace["received"] = {
                "http_status": r.get("http_status"),
                "body_bytes": r.get("body_bytes"),
                "text_bytes": len(text.encode("utf-8")),
                "text_sha256": _sha256_text(text),
                "response_text_raw": text,
                "provider": r.get("provider"),
                "url": r.get("url"),
                "model": r.get("model"),
                "error": r.get("error"),
            }

            if not text.strip():
                raise RuntimeError("no_text_in_response")

            try:
                cleaned = _sanitize_jsonish_text(text)
                cleaned_json = _extract_first_json_object(cleaned)
                cleaned_path.write_text(cleaned_json, encoding="utf-8")
                print("--- response_text_cleaned ---")
                print(cleaned_json)
                trace["received"]["response_text_cleaned"] = cleaned_json
                obj = _validate_obj_for_schema(json.loads(cleaned_json), schema_name)
                if schema_name == "timeline.phase2.v1":
                    obj = _prune_timeline_phase2_obj(obj)
            except Exception as parse_err:
                trace["repair"]["initial_parse_error"] = f"{type(parse_err).__name__}: {parse_err}"
                obj = _deterministic_fallback_from_text(text, dom, schema_name)
                cleaned_json = json.dumps(obj, ensure_ascii=False, indent=2)
                cleaned_path.write_text(cleaned_json, encoding="utf-8")
                trace["repair"]["used_deterministic_fallback"] = True
                trace["repair"]["fallback_json"] = cleaned_json

            obj = _validate_obj_for_schema(obj, schema_name)
            write_json(findings_path, obj)
            write_json(latest_findings_path, obj)

            trace["ok"] = True

        except Exception as e:
            any_fail = True
            trace["ok"] = False
            trace["error"] = f"{type(e).__name__}: {e}"
            trace["traceback"] = traceback.format_exc()

        finally:
            trace["ended_at"] = _now_iso()
            trace["elapsed_ms"] = int((time.time() - dom_t0) * 1000)
            write_json(trace_run_path, trace)
            write_json(trace_latest_path, trace)

            print(f"\n===== PHASE2 TRACE [{dom}] =====")
            print(json.dumps(trace, ensure_ascii=False, indent=2))

    for dom in domains:
        cfg = load_domain_config(infra_dir, dom)
        if not phase_enabled(cfg, "phase2"):
            print(f"\n===== PHASE2 SKIP [{dom}] reason=phase2_disabled_in_config =====")
            continue
        _run_one_domain(dom)

    out["ok"] = not any_fail
    out["ended_at"] = _now_iso()
    out["elapsed_ms"] = int((time.time() - t0) * 1000)

    print("\n===== PHASE2 SUMMARY =====")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out
