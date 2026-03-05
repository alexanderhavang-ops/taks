from __future__ import annotations

import hashlib
import json
import os
import time
import traceback
import urllib.request
from pathlib import Path
from typing import Any, Dict, Tuple

from takctl.services.llm2.paths import runs_root, latest_root
from takctl.services.llm2.store import write_json

CARD_KEYS = ("headline", "subtitle", "graphic", "lede", "body", "details_hint")
GRAPHIC_KEYS = ("type", "data", "note")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _read_json(p: Path) -> Any:
    return json.loads(_read_text(p))


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha256_text(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8", errors="replace")).hexdigest()


def _sanitize_jsonish_text(raw: str) -> str:
    # Same behavior as phase2, kept local to avoid import cycles.
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
    if i_obj == -1:
        return t
    end = t.rfind("}")
    if end == -1 or end < i_obj:
        return t[i_obj:].strip()
    return t[i_obj : end + 1].strip()


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


def _extract_text(resp_obj: Any) -> str:
    try:
        if isinstance(resp_obj, dict) and (resp_obj.get("choices") or []):
            ch0 = (resp_obj.get("choices") or [{}])[0] or {}
            if isinstance(ch0, dict) and "text" in ch0:
                return ch0.get("text") or ""
    except Exception:
        pass
    return ""


def _llama_post(url: str, payload: Dict[str, Any], timeout_s: int) -> Dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        method="POST",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        body = resp.read()
        return {"status": resp.status, "body_bytes": body}


def _phase2_gate(latest_dom_dir: Path) -> Tuple[bool, str]:
    p_trace = latest_dom_dir / "phase2" / "trace.json"
    p_findings = latest_dom_dir / "phase2" / "findings.json"

    if not p_trace.exists():
        return False, "phase2_trace_missing"
    if not p_findings.exists():
        return False, "phase2_findings_missing"

    try:
        trace = _read_json(p_trace)
    except Exception:
        return False, "phase2_trace_invalid_json"

    if not trace.get("ok", False):
        return False, f"phase2_failed:{trace.get('error')}"

    return True, "ok"


def _load_prompt(infra_dir: Path, dom: str) -> Tuple[str, str]:
    sys_p = infra_dir / "domains" / dom / "prompts" / "phase3" / "system.txt"
    usr_p = infra_dir / "domains" / dom / "prompts" / "phase3" / "user.txt"
    system_txt = _read_text(sys_p).strip()
    user_txt = _read_text(usr_p).strip()
    if not system_txt:
        system_txt = "You produce an operator-facing card based on findings."
    return system_txt, user_txt


def _build_prompt(system_txt: str, user_txt: str, findings_json: str) -> str:
    parts = []
    if system_txt.strip():
        parts.append(system_txt.strip())
        parts.append("")
    if user_txt.strip():
        parts.append(user_txt.strip())
        parts.append("")
    parts.append("## INPUT_FINDINGS_JSON")
    parts.append(findings_json.strip())
    parts.append("")
    return "\n".join(parts).strip() + "\n"


def _validate_card(obj: Any) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        raise RuntimeError("not_a_json_object")

    for k in CARD_KEYS:
        if k not in obj:
            raise RuntimeError(f"missing_key:{k}")

    # strings
    for k in ("headline", "subtitle", "lede", "body", "details_hint"):
        v = obj.get(k)
        if not isinstance(v, str):
            obj[k] = "" if v is None else str(v)

    # graphic object
    g = obj.get("graphic")
    if not isinstance(g, dict):
        g = {}
    gt = g.get("type")
    if not isinstance(gt, str):
        gt = "none"
    if gt not in ("none", "sparkline", "bar", "timeline", "map_stub"):
        gt = "none"
    gd = g.get("data")
    if not isinstance(gd, dict):
        gd = {}
    gn = g.get("note")
    if not isinstance(gn, str):
        gn = "" if gn is None else str(gn)
    obj["graphic"] = {"type": gt, "data": gd, "note": gn}

    # no extra keys (keep it tight/deterministic)
    obj2 = {k: obj.get(k) for k in CARD_KEYS}
    return obj2


def run_phase3(*, run_id: str) -> Dict[str, Any]:
    started = _now_iso()
    t0 = time.time()

    infra_dir = Path(os.environ.get("TAKCTL_LLM2_INFRA_DIR", "/opt/tak/tools/takctl/llm-infra"))
    llm_url = os.environ.get("TAKCTL_LLM_URL", "http://127.0.0.1:8090/v1/completions")
    model = os.environ.get("TAKCTL_LLM_MODEL", "local-small")

    timeout_s = int(os.environ.get("TAKCTL_LLM_TIMEOUT_S", "900"))
    n_predict = int(os.environ.get("TAKCTL_LLM_N_PREDICT", "700"))
    temperature = float(os.environ.get("TAKCTL_LLM_TEMPERATURE", "0.2"))

    domains = ["chatter", "missions", "_summary"]

    out: Dict[str, Any] = {
        "ok": True,
        "run_id": run_id,
        "phase": "phase3",
        "started_at": started,
        "llm_url": llm_url,
        "llm_model": model,
        "timeout_s": timeout_s,
        "n_predict": n_predict,
        "temperature": temperature,
        "stop": ["}\\n"],
    }

    any_fail = False

    (runs_root() / run_id).mkdir(parents=True, exist_ok=True)
    latest_root().mkdir(parents=True, exist_ok=True)

    for dom in domains:
        dom_t0 = time.time()
        dom_started = _now_iso()

        latest_dom_dir = latest_root() / dom
        run_dom_dir = runs_root() / run_id / dom / "phase3"
        run_dom_dir.mkdir(parents=True, exist_ok=True)

        latest_phase3_dir = latest_dom_dir / "phase3"
        latest_phase3_dir.mkdir(parents=True, exist_ok=True)

        req_path = run_dom_dir / "request.json"
        prompt_path = run_dom_dir / "prompt.txt"
        resp_http_path = run_dom_dir / "response.http.json"
        resp_raw_path = run_dom_dir / "response_raw.json"
        resp_text_path = run_dom_dir / "response_text.txt"
        cleaned_path = run_dom_dir / "cleaned_text.txt"
        card_path = run_dom_dir / "card.json"

        latest_json_path = latest_phase3_dir / "latest.json"
        trace_run_path = run_dom_dir / "trace.json"
        trace_latest_path = latest_phase3_dir / "trace.json"

        trace: Dict[str, Any] = {
            "phase": "phase3",
            "domain": dom,
            "run_id": run_id,
            "started_at": dom_started,
            "ok": False,
            "llm_url": llm_url,
            "llm_model": model,
            "timeout_s": timeout_s,
            "n_predict": n_predict,
            "temperature": temperature,
            "phase2_gate": None,
            "error": None,
            "sent": {},
            "received": {},
            "files": {
                "request_path": str(req_path),
                "prompt_path": str(prompt_path),
                "response_http_path": str(resp_http_path),
                "response_raw_path": str(resp_raw_path),
                "response_text_path": str(resp_text_path),
                "cleaned_text_path": str(cleaned_path),
                "card_path": str(card_path),
                "latest_json_path": str(latest_json_path),
                "trace_path": str(trace_latest_path),
                "trace_run_path": str(trace_run_path),
            },
        }

        try:
            ok, reason = _phase2_gate(latest_dom_dir)
            trace["phase2_gate"] = {"ok": ok, "reason": reason}
            if not ok:
                # deterministic fallback card
                card = {
                    "headline": f"No findings ({reason}).",
                    "subtitle": "",
                    "graphic": {"type": "none", "data": {}, "note": ""},
                    "lede": "",
                    "body": "",
                    "details_hint": "Click for raw evidence and traces.",
                    "_meta": {"domain": dom, "run_id": run_id, "generated_utc": _now_iso()},
                }
                write_json(card_path, card)
                write_json(latest_json_path, card)
                trace["ok"] = True
                trace["note"] = "phase3_short_circuit_no_phase2_findings"
                continue

            # Load phase2 findings
            p2_findings = latest_dom_dir / "phase2" / "findings.json"
            findings_obj = _read_json(p2_findings)
            findings_json = json.dumps(findings_obj, ensure_ascii=False, indent=2, sort_keys=True)

            system_txt, user_txt = _load_prompt(infra_dir, dom)
            prompt = _build_prompt(system_txt, user_txt, findings_json)

            prompt_path.write_text(prompt, encoding="utf-8")

            payload: Dict[str, Any] = {
                "model": model,
                "seed": 7,
                "temperature": temperature,
                "n_predict": n_predict,
                "prompt": prompt,
            }
            write_json(req_path, {"url": llm_url, "payload": payload})

            # Call model
            resp = _llama_post(llm_url, payload, timeout_s=timeout_s)
            http_status = int(resp.get("status") or 0)
            body_bytes = resp.get("body_bytes") or b""

            resp_http_path.write_text(
                json.dumps(
                    {
                        "status": http_status,
                        "body_bytes_len": len(body_bytes),
                        "body_utf8": body_bytes.decode("utf-8", errors="replace"),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            body_text = body_bytes.decode("utf-8", errors="replace")
            try:
                body_obj = json.loads(body_text or "{}")
            except Exception:
                body_obj = {"_raw": body_text}
            write_json(resp_raw_path, body_obj)

            text = _extract_text(body_obj)
            resp_text_path.write_text(text or "", encoding="utf-8")

            cleaned = _sanitize_jsonish_text(text or "")
            cleaned_path.write_text(cleaned or "", encoding="utf-8")

            trace["sent"] = {
                "prompt_sha256": _sha256_text(prompt),
                "prompt_bytes": len(prompt.encode("utf-8")),
            }
            trace["received"] = {
                "http_status": http_status,
                "http_bytes": len(body_bytes),
                "http_sha256": _sha256_bytes(body_bytes),
                "text_bytes": len((text or "").encode("utf-8")),
                "text_sha256": _sha256_text(text or ""),
            }

            if not (text or "").strip():
                raise RuntimeError("no_text_in_response")

            raw_json = _extract_first_json_object(cleaned)
            obj = json.loads(raw_json)
            card_core = _validate_card(obj)

            card = dict(card_core)
            card["_meta"] = {"domain": dom, "run_id": run_id, "generated_utc": _now_iso()}
            write_json(card_path, card)
            write_json(latest_json_path, card)

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

    out["ok"] = not any_fail
    out["ended_at"] = _now_iso()
    out["elapsed_ms"] = int((time.time() - t0) * 1000)
    return out
