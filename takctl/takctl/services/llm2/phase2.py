from __future__ import annotations


def _extract_first_json_object(text: str) -> str:
    """
    Robustly salvage the FIRST JSON object from messy LLM output.

    Handles:
      - leading junk (markdown, prose, multiple headings) -> ignored until first '{'
      - trailing junk after object -> ignored
      - multiple JSON objects -> returns the first complete one
      - truncated output missing final '}' -> attempts to auto-close braces
      - stray backticks / "## OUTPUT_JSON" etc around JSON -> ignored

    Strategy:
      1) Find first '{'. If none -> ValueError
      2) Scan forward with a brace counter (string/escape aware) to find the end
         of the first object. If found -> return that slice.
      3) If we hit end-of-text before braces close -> append missing '}' braces and return.
    """
    if not text:
        raise ValueError("empty_text")

    s = text
    i0 = s.find("{")
    if i0 < 0:
        raise ValueError("no_json_object_start")

    # Start scanning at the first '{'
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

        # not in string
        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                end_idx = idx + 1  # slice end is exclusive
                break
            continue

    if end_idx is None:
        # truncated: auto-close braces (only if we were not inside a string;
        # if we are inside a string at EOF, we cannot safely salvage)
        if in_str:
            raise ValueError("truncated_inside_string")

        if depth <= 0:
            # Weird, but just try to parse up to last '}' if any
            j = s.rfind("}")
            if j >= 0:
                return s[: j + 1]
            raise ValueError("no_closing_brace_found")

        return s + ("}" * depth)

    return s[:end_idx]


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

REQ_KEYS = ("important", "newest", "details")


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
    """
    Ported from the old working pipeline (ops_findings_phase2.py).

    Make parsing resilient to common llama.cpp / small-instruct quirks:
      - leading/trailing whitespace
      - one or more markdown fences (``` or ```json), sometimes preceded by a stray ``` block
      - extra text before/after JSON (slice to first {/[ and last }/])
    """
    t = (raw or "").strip()
    if not t:
        return t

    # Drop any number of leading fence lines and blank lines.
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

    # Drop trailing fence if present
    lines = t.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and lines[-1].strip() == "```":
        lines.pop()
    t = "\n".join(lines).strip()

    if not t:
        return t

    # Slice to JSON payload (best-effort)
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


def _extract_text(resp_obj: Any) -> str:
    """
    Support OpenAI-like completion shape:
      {"choices":[{"text":"..."}], ...}
    """
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


def _phase1_evidence_text(latest_dom_dir: Path) -> str:
    p_latest = latest_dom_dir / "phase1" / "latest.json"
    if not p_latest.exists():
        return ""
    try:
        return json.dumps(_read_json(p_latest), ensure_ascii=False, indent=2, sort_keys=True)
    except Exception:
        return _read_text(p_latest)


def _load_prompt(infra_dir: Path, dom: str) -> Tuple[str, str]:
    sys_p = infra_dir / "domains" / dom / "prompts" / "phase2" / "system.txt"
    usr_p = infra_dir / "domains" / dom / "prompts" / "phase2" / "user.txt"
    system_txt = _read_text(sys_p).strip()
    user_txt = _read_text(usr_p).strip()
    if not system_txt:
        # keep it mild like old pipeline
        system_txt = "You produce operational findings based on the provided input."
    return system_txt, user_txt


def _build_prompt(system_txt: str, user_txt: str, evidence_json: str) -> str:
    """
    Old pipeline style:
      system + user + marker + JSON
    The prompt pack carries the JSON shape and guidance.
    """
    parts = []
    if system_txt.strip():
        parts.append(system_txt.strip())
        parts.append("")
    if user_txt.strip():
        parts.append(user_txt.strip())
        parts.append("")
    parts.append("## INPUT_EVIDENCE_JSON")
    parts.append(evidence_json.strip())
    parts.append("")
    return "\n".join(parts).strip() + "\n"


def _validate_obj(obj: Any) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        raise RuntimeError("not_a_json_object")
    for k in REQ_KEYS:
        if k not in obj:
            raise RuntimeError(f"missing_key:{k}")
    for k in REQ_KEYS:
        if not isinstance(obj.get(k), str):
            obj[k] = "" if obj.get(k) is None else str(obj.get(k))
    return obj


def run_phase2(*, run_id: str) -> Dict[str, Any]:
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
        "phase": "phase2",
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
            "llm_url": llm_url,
            "llm_model": model,
            "timeout_s": timeout_s,
            "n_predict": n_predict,
            "temperature": temperature,
            "phase1_gate": None,
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
                "findings_path": str(findings_path),
                "latest_findings_path": str(latest_findings_path),
                "trace_path": str(trace_latest_path),
                "trace_run_path": str(trace_run_path),
            },
        }

        try:
            ok, reason = _phase1_gate(latest_dom_dir)
            trace["phase1_gate"] = {"ok": ok, "reason": reason}
            if not ok:
                print(f"\n===== PHASE2 SKIP [{dom}] reason={reason} =====")
                obj = {"important": f"No evidence ({reason}).", "newest": "", "details": ""}
                write_json(findings_path, obj)
                write_json(latest_findings_path, obj)
                trace["ok"] = True
                trace["note"] = "phase2_short_circuit_no_phase1_evidence"
                continue

            evidence = _phase1_evidence_text(latest_dom_dir)
            if not evidence.strip():
                print(f"\n===== PHASE2 SKIP [{dom}] reason=phase1_latest_empty =====")
                obj = {"important": "No evidence.", "newest": "", "details": ""}
                write_json(findings_path, obj)
                write_json(latest_findings_path, obj)
                trace["ok"] = True
                trace["note"] = "phase2_short_circuit_empty_evidence"
                continue

            system_txt, user_txt = _load_prompt(infra_dir, dom)
            prompt = _build_prompt(system_txt, user_txt, evidence)

            # Persist FULL prompt (required)
            prompt_path.write_text(prompt, encoding="utf-8")

            payload: Dict[str, Any] = {
                "model": model,
                "seed": 7,
                "temperature": temperature,
                "n_predict": n_predict,
                "prompt": prompt,
            }
            write_json(req_path, {"url": llm_url, "payload": payload})

            # ---- SENT: FULL PROMPT (stdout + trace) ----
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

            # Call model
            resp = _llama_post(llm_url, payload, timeout_s=timeout_s)
            http_status = int(resp.get("status") or 0)
            body_bytes = resp.get("body_bytes") or b""

            # Persist verbatim HTTP wrapper
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

            # ---- RECEIVED: SALVAGED JSON ONLY (stdout + trace) ----
            cleaned = _sanitize_jsonish_text(text or "")
            cleaned_json = _extract_first_json_object(cleaned)
            cleaned_path.write_text(cleaned_json or "", encoding="utf-8")

            print(f"\n===== PHASE2 RECEIVED [{dom}] =====")
            print(f"http_status={http_status} http_bytes={len(body_bytes)} http_sha256={_sha256_bytes(body_bytes)}")
            print(f"text_bytes={len((text or '').encode('utf-8'))} text_sha256={_sha256_text(text or '')}")
            print("--- response_text_raw ---")
            print(text or "")
            print("--- response_text_cleaned ---")
            print(cleaned_json or "")

            trace["received"] = {
                "http_status": http_status,
                "http_bytes": len(body_bytes),
                "http_sha256": _sha256_bytes(body_bytes),
                "text_bytes": len((text or "").encode("utf-8")),
                "text_sha256": _sha256_text(text or ""),
                "response_text_raw": text or "",
                "response_text_cleaned": cleaned_json or "",
            }

            if not (text or "").strip():
                raise RuntimeError("no_text_in_response")

            obj = _validate_obj(json.loads(cleaned_json))
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

    out["ok"] = not any_fail
    out["ended_at"] = _now_iso()
    out["elapsed_ms"] = int((time.time() - t0) * 1000)

    print("\n===== PHASE2 SUMMARY =====")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out
