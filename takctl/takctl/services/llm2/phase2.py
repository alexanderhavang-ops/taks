from __future__ import annotations

import hashlib
import json
import os
import re
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Tuple

from takctl.services.llm2.llm_client import LlmClient
from takctl.services.llm2.paths import runs_root, latest_root
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

    # strip common fences
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
    return (os.environ.get("TAKCTL_LLM2_PHASE2_EVIDENCE_PROFILE", "compact") or "compact").strip().lower()


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


def _phase1_evidence_text(latest_dom_dir: Path, dom: str) -> str:
    p_latest = latest_dom_dir / "phase1" / "latest.json"
    if not p_latest.exists():
        return ""

    try:
        obj = _read_json(p_latest)
    except Exception:
        return _read_text(p_latest)

    chosen_profile, chosen_payload = _select_profile_payload_from_phase1(obj)
    if chosen_payload is not None:
        return json.dumps(chosen_payload, ensure_ascii=False, indent=2, sort_keys=True)

    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


def _load_prompt(infra_dir: Path, dom: str) -> Tuple[str, str]:
    sys_p = infra_dir / "domains" / dom / "prompts" / "phase2" / "system.txt"
    usr_p = infra_dir / "domains" / dom / "prompts" / "phase2" / "user.txt"
    system_txt = _read_text(sys_p).strip()
    user_txt = _read_text(usr_p).strip()
    if not system_txt:
        system_txt = "You produce operational findings based on the provided input."
    return system_txt, user_txt


def _build_prompt(system_txt: str, user_txt: str, evidence_json: str) -> str:
    parts = []
    if system_txt.strip():
        parts.append(system_txt.strip())
        parts.append("")
    if user_txt.strip():
        parts.append(user_txt.strip())
        parts.append("")
    parts.append("## INPUT")
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


def _deterministic_fallback_from_text(raw_text: str, dom: str) -> Dict[str, str]:
    s = _strip_json_noise(raw_text)
    sentences = _pick_sentences(s, 6)

    important = sentences[0] if sentences else f"{dom} findings unavailable."
    newest = sentences[1] if len(sentences) > 1 else ""
    details = " ".join(sentences[2:6]) if len(sentences) > 2 else s[:600]

    if not details:
        details = important

    return {
        "important": important[:400].strip(),
        "newest": newest[:400].strip(),
        "details": details[:1200].strip(),
    }


def _repair_response_with_llm(
    *,
    client: LlmClient,
    raw_text: str,
    evidence_json: str,
) -> Dict[str, Any]:
    repair_prompt = (
        "Return JSON only.\n"
        "First character must be { and last character must be }.\n"
        "Return exactly these keys: important, newest, details.\n"
        "All three values must be strings.\n"
        "Do not include any other keys.\n"
        "Do not repeat INPUT.\n"
        "If RAW_RESPONSE is malformed or truncated, salvage the intended meaning.\n"
        "If RAW_RESPONSE is useless, use INPUT_EVIDENCE conservatively.\n\n"
        "## RAW_RESPONSE\n"
        f"{(raw_text or '')[:3000]}\n\n"
        "## INPUT_EVIDENCE\n"
        f"{(evidence_json or '')[:3000]}\n"
    )

    r = client.complete_text(prompt=repair_prompt, temperature=0.0, max_tokens=260, seed=7)
    text = r.get("text") or ""
    cleaned = _sanitize_jsonish_text(text)
    cleaned_json = _extract_first_json_object(cleaned)
    obj = _validate_obj(json.loads(cleaned_json))

    return {
        "obj": obj,
        "llm": r,
        "prompt": repair_prompt,
        "cleaned_json": cleaned_json,
        "text": text,
    }


def _gather_phase2_findings_for_summary(*, latest_dir: Path) -> Dict[str, Any]:
    domains: Dict[str, Any] = {}
    if not latest_dir.exists():
        return {"ok": False, "error": "latest_root_missing", "domains": domains}

    for dom_dir in sorted([p for p in latest_dir.iterdir() if p.is_dir()]):
        dom = dom_dir.name
        if dom == "_summary":
            continue

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

        reduced: Dict[str, str] = {}
        for k in REQ_KEYS:
            v = fo.get(k)
            if v is None:
                reduced[k] = ""
            elif isinstance(v, str):
                reduced[k] = v
            else:
                reduced[k] = str(v)

        entry["ok"] = bool(reduced.get("important") or reduced.get("newest") or reduced.get("details"))
        entry["findings"] = reduced
        domains[dom] = entry

    return {"ok": True, "generated_utc": _now_iso(), "domains": domains}


def run_phase2(*, run_id: str) -> Dict[str, Any]:
    started = _now_iso()
    t0 = time.time()

    infra_dir = Path(os.environ.get("TAKCTL_LLM2_INFRA_DIR", "/opt/tak/tools/takctl/llm-infra"))

    # LLM config comes from llm.env via LlmClient()
    client = LlmClient()

    n_predict = int(os.environ.get("TAKCTL_LLM_N_PREDICT", "700"))
    temperature = float(os.environ.get("TAKCTL_LLM_TEMPERATURE", "0.2"))

    domains = sorted([p.name for p in latest_root().iterdir() if p.is_dir() and p.name != "_summary"]) if latest_root().exists() else []

    out: Dict[str, Any] = {
        "ok": True,
        "run_id": run_id,
        "phase": "phase2",
        "started_at": started,
        "provider": getattr(client, "provider", None),
        "model": (client.bedrock_model_id if getattr(client, "provider", "") == "bedrock" else client.model),
        "n_predict": n_predict,
        "temperature": temperature,
        "domains": domains + ["_summary"],
        "summary_enabled": True,
        "env_path": getattr(client, "env_path", None),
    }

    any_fail = False

    (runs_root() / run_id).mkdir(parents=True, exist_ok=True)
    latest_root().mkdir(parents=True, exist_ok=True)

    def _run_one_domain(
        dom: str, *, evidence_override_json: str | None = None, phase1_gate_override: Tuple[bool, str] | None = None
    ) -> None:
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
            if phase1_gate_override is not None:
                ok, reason = phase1_gate_override
            else:
                ok, reason = _phase1_gate(latest_dom_dir)
            trace["phase1_gate"] = {"ok": ok, "reason": reason}

            if not ok and evidence_override_json is None:
                print(f"\n===== PHASE2 SKIP [{dom}] reason={reason} =====")
                obj = {"important": f"No evidence ({reason}).", "newest": "", "details": ""}
                write_json(findings_path, obj)
                write_json(latest_findings_path, obj)
                trace["ok"] = True
                trace["note"] = "phase2_short_circuit_no_phase1_evidence"
                return

            if evidence_override_json is not None:
                evidence = evidence_override_json
            else:
                evidence = _phase1_evidence_text(latest_dom_dir, dom)

            if not evidence.strip():
                print(f"\n===== PHASE2 SKIP [{dom}] reason=empty_evidence =====")
                obj = {"important": "No evidence.", "newest": "", "details": ""}
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

            r = client.complete_text(prompt=prompt, temperature=temperature, max_tokens=n_predict, seed=7)
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

            obj: Dict[str, str] | None = None
            cleaned_json = ""

            try:
                cleaned = _sanitize_jsonish_text(text)
                cleaned_json = _extract_first_json_object(cleaned)
                cleaned_path.write_text(cleaned_json, encoding="utf-8")
                print("--- response_text_cleaned ---")
                print(cleaned_json)
                trace["received"]["response_text_cleaned"] = cleaned_json
                obj = _validate_obj(json.loads(cleaned_json))
            except Exception as parse_err:
                trace["repair"]["initial_parse_error"] = f"{type(parse_err).__name__}: {parse_err}"

                try:
                    repaired = _repair_response_with_llm(
                        client=client,
                        raw_text=text,
                        evidence_json=evidence,
                    )
                    obj = repaired["obj"]
                    cleaned_json = repaired["cleaned_json"]
                    cleaned_path.write_text(cleaned_json, encoding="utf-8")
                    trace["repair"]["used_llm_repair"] = True
                    trace["repair"]["repair_llm"] = {
                        "provider": repaired["llm"].get("provider"),
                        "url": repaired["llm"].get("url"),
                        "model": repaired["llm"].get("model"),
                        "http_status": repaired["llm"].get("http_status"),
                        "error": repaired["llm"].get("error"),
                    }
                    trace["repair"]["repair_prompt"] = repaired["prompt"]
                    trace["repair"]["repair_text"] = repaired["text"]
                    trace["repair"]["repair_cleaned_json"] = repaired["cleaned_json"]
                except Exception as repair_err:
                    trace["repair"]["used_llm_repair"] = False
                    trace["repair"]["repair_error"] = f"{type(repair_err).__name__}: {repair_err}"
                    obj = _deterministic_fallback_from_text(text, dom)
                    cleaned_json = json.dumps(obj, ensure_ascii=False, indent=2)
                    cleaned_path.write_text(cleaned_json, encoding="utf-8")
                    trace["repair"]["used_deterministic_fallback"] = True
                    trace["repair"]["fallback_json"] = cleaned_json

            obj = _validate_obj(obj)
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

    # 1) normal domains
    for dom in domains:
        _run_one_domain(dom)

    # 2) summary domain: evidence is synthesized from other phase2 findings (first-class)
    summary_payload = _gather_phase2_findings_for_summary(latest_dir=latest_root())
    summary_evidence = json.dumps(summary_payload, ensure_ascii=False, indent=2, sort_keys=True)
    _run_one_domain("_summary", evidence_override_json=summary_evidence, phase1_gate_override=(True, "ok"))

    out["ok"] = not any_fail
    out["ended_at"] = _now_iso()
    out["elapsed_ms"] = int((time.time() - t0) * 1000)

    print("\n===== PHASE2 SUMMARY =====")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out
