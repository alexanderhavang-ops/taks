from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
import traceback
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

from takctl.services.llm2.paths import runs_root, latest_root
from takctl.services.llm2.store import write_json


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


def _extract_text(resp_obj: Any) -> str:
    try:
        if isinstance(resp_obj, dict) and (resp_obj.get("choices") or []):
            ch0 = (resp_obj.get("choices") or [{}])[0] or {}
            if isinstance(ch0, dict) and "text" in ch0:
                return ch0.get("text") or ""
    except Exception:
        pass
    return ""


# ---------------- prompt loading ----------------

def _load_prompt(infra_dir: Path, dom: str) -> Tuple[str, str]:
    sys_p = infra_dir / "domains" / dom / "prompts" / "phase3" / "system.txt"
    usr_p = infra_dir / "domains" / dom / "prompts" / "phase3" / "user.txt"

    system_txt = _read_text(sys_p).strip()
    user_txt = _read_text(usr_p).strip()

    # Hard safety fallback if missing
    if not system_txt:
        system_txt = (
            "You generate an operator-facing HTML card for a tactical dashboard.\n"
            "OUTPUT MUST BE HTML ONLY. No JSON. No markdown fences.\n"
            "Output exactly ONE card: a single <div>...</div>.\n"
            "Safety: no script/style/iframe/object/embed/link/meta, no onclick=, no javascript: URLs.\n"
            "Factuality: do not invent facts.\n"
        )
    if not user_txt:
        user_txt = f'Create a compact operator-facing HTML card for domain "{dom}".'

    # Guard against legacy drift: strip JSON instructions
    def _strip_legacy(s: str) -> str:
        lines = []
        for ln in (s or "").splitlines():
            u = ln.upper()
            if "OUTPUT MUST BE VALID JSON" in u:
                continue
            if "RETURN EXACTLY THIS JSON" in u:
                continue
            if "JSON ONLY" in u:
                continue
            lines.append(ln)
        return "\n".join(lines).strip()

    return _strip_legacy(system_txt), _strip_legacy(user_txt)


def _build_prompt(system_txt: str, user_txt: str, findings_json: str) -> str:
    # IMPORTANT: do NOT include placeholder examples like ".." or "..." because local-small parrots them.
    parts: List[str] = []
    if system_txt.strip():
        parts.append(system_txt.strip())
        parts.append("")
    if user_txt.strip():
        parts.append(user_txt.strip())
        parts.append("")

    parts.append("Input is Phase2 findings JSON with keys: important, newest, details.")
    parts.append("")
    parts.append("OUTPUT RULES (STRICT):")
    parts.append("- Start immediately with '<div>' (first non-whitespace characters).")
    parts.append("- Output exactly ONE HTML card: a single <div> ... </div>.")
    parts.append("- Use only these tags: div, h3, p, ul, li, strong, em, br.")
    parts.append("- Do NOT repeat instructions or include any prose outside the single <div>.")
    parts.append("- Do NOT output placeholders like '..' or '...'.")
    parts.append("- Do not invent facts.")
    parts.append("")
    parts.append("## INPUT_FINDINGS_JSON")
    parts.append(findings_json.strip())
    parts.append("")
    return "\n".join(parts).strip() + "\n"


# ---------------- gating & inputs ----------------

def _phase2_gate(latest_dom_dir: Path) -> Tuple[bool, str]:
    p_findings = latest_dom_dir / "phase2" / "findings.json"
    p_trace = latest_dom_dir / "phase2" / "trace.json"
    if not p_findings.exists():
        return False, "phase2_findings_missing"
    if not p_trace.exists():
        return False, "phase2_trace_missing"
    try:
        trace = _read_json(p_trace)
    except Exception:
        return False, "phase2_trace_invalid_json"
    if not trace.get("ok", False):
        return False, f"phase2_failed:{trace.get('error')}"
    return True, "ok"


def _phase2_findings_obj(latest_dom_dir: Path) -> Dict[str, Any]:
    p = latest_dom_dir / "phase2" / "findings.json"
    if not p.exists():
        return {}
    try:
        o = _read_json(p)
        return o if isinstance(o, dict) else {}
    except Exception:
        return {}


def _phase2_findings_text(latest_dom_dir: Path) -> str:
    o = _phase2_findings_obj(latest_dom_dir)
    return json.dumps(o, ensure_ascii=False, indent=2, sort_keys=True) if o else ""


def _findings_values(findings: Dict[str, Any]) -> List[str]:
    vals: List[str] = []
    for k in ("important", "newest", "details"):
        v = findings.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            vals.append(s)
    # de-dupe while preserving order
    out: List[str] = []
    seen = set()
    for s in vals:
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _fallback_card(dom: str, findings: Dict[str, Any]) -> str:
    # Deterministic, always clean.
    title = dom
    important = (str(findings.get("important") or "")).strip()
    newest = (str(findings.get("newest") or "")).strip()
    details = (str(findings.get("details") or "")).strip()

    # headline: prefer something meaningful
    if important:
        title = important
    elif newest:
        title = newest
    elif details:
        title = details

    bullets = []
    if newest and newest != title:
        bullets.append(newest)
    if details and details != title and details != newest:
        bullets.append(details)
    if important and important != title and important != newest and important != details:
        bullets.append(important)

    # cap bullets
    bullets = bullets[:6]

    esc_title = html.escape(title)
    sub = newest or (important if important != title else "") or ""
    esc_sub = html.escape(sub) if sub else ""
    li = "\n".join([f"    <li>{html.escape(b)}</li>" for b in bullets]) if bullets else ""

    if li:
        return f"<div><h3>{esc_title}</h3><p>{esc_sub}</p><ul>\n{li}\n  </ul></div>" if esc_sub else f"<div><h3>{esc_title}</h3><ul>\n{li}\n  </ul></div>"
    else:
        # at least show something
        if details and details != title:
            return f"<div><h3>{esc_title}</h3><p>{html.escape(details)}</p></div>"
        return f"<div><h3>{esc_title}</h3></div>"


# ---------------- sanitize / extract ----------------

_ALLOWED_TAGS = {"div", "h3", "p", "ul", "li", "strong", "em", "br"}

_BAD_TAG_BLOCK_RE = re.compile(r"(?is)<\s*(script|style|iframe|object|embed)\b[^>]*>.*?<\s*/\s*\1\s*>")
_BAD_SINGLE_TAG_RE = re.compile(r"(?is)<\s*(script|style|iframe|object|embed|link|meta)\b[^>]*?/?>")
_ONATTR_RE = re.compile(r'(?is)\s+on[a-zA-Z]+\s*=\s*(".*?"|\'.*?\'|[^\s>]+)')
_JSURL_RE = re.compile(r'(?is)\s+(href|src)\s*=\s*("|\')\s*javascript:.*?\2')
_JUNK_TAGS_RE = re.compile(r"(?is)</?\s*(commit_msg|commit_after)\b[^>]*>")

# extract all div blocks
_DIV_RE = re.compile(r"(?is)<div\b[^>]*>.*?</div>")

# placeholders that local-small likes to output when it parrots instructions
_PLACEHOLDER_RE = re.compile(r"(?is)\.\.\.|<h3>\s*\.\.\s*</h3>|<p>\s*\.\.\s*</p>|<li>\s*\.\.\s*</li>")


def _strip_disallowed_tags_keep_text(s: str) -> str:
    def repl(m: re.Match) -> str:
        tag = (m.group(1) or "").lower()
        return m.group(0) if tag in _ALLOWED_TAGS else ""

    return re.sub(r"(?is)</?\s*([a-zA-Z0-9:_-]+)\b[^>]*>", repl, s)


def _sanitize_html_fragment(frag: str) -> str:
    frag = _BAD_TAG_BLOCK_RE.sub("", frag)
    frag = _BAD_SINGLE_TAG_RE.sub("", frag)
    frag = _JUNK_TAGS_RE.sub("", frag)
    frag = _ONATTR_RE.sub("", frag)
    frag = _JSURL_RE.sub("", frag)
    frag = _strip_disallowed_tags_keep_text(frag)
    frag = re.sub(r"\n{4,}", "\n\n", frag).strip()
    return frag


def _extract_best_div_or_fallback(raw: str, dom: str, findings: Dict[str, Any]) -> str:
    t = (raw or "").strip()
    vals = _findings_values(findings)

    # If fenced ```html exists, prefer inside
    m = re.search(r"(?is)```html\s*(.*?)\s*```", t)
    if m and (m.group(1) or "").strip():
        t = (m.group(1) or "").strip()

    divs = _DIV_RE.findall(t)

    def score(div: str) -> int:
        d = div or ""
        if _PLACEHOLDER_RE.search(d):
            return -9999
        # prefer divs that contain any of the input values
        s = 0
        for v in vals:
            if not v:
                continue
            if v in d:
                s += 1000
            else:
                # tiny partial credit for substring pieces
                # (helps when model escapes quotes etc)
                piece = v[:40]
                if piece and piece in d:
                    s += 100
        # penalize if it contains instruction-ish phrases
        if "Output must" in d or "OUTPUT RULES" in d or "Start immediately" in d:
            s -= 500
        return s

    best = None
    best_score = -10**9
    for d in divs:
        s = score(d)
        if s > best_score:
            best = d
            best_score = s

    if best and best_score > 0:
        cleaned = _sanitize_html_fragment(best)
        # ensure single outer div boundary
        cleaned = cleaned.strip()
        if not cleaned.lower().startswith("<div"):
            cleaned = "<div>" + cleaned + "</div>"
        if not cleaned.lower().endswith("</div>"):
            cleaned = cleaned + "</div>"
        # final placeholder guard
        if not _PLACEHOLDER_RE.search(cleaned):
            return cleaned

    # Nothing usable produced -> deterministic fallback
    return _fallback_card(dom, findings)


# ---------------- main ----------------

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

        latest_path = latest_phase3_dir / "latest.json"
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
        }

        try:
            ok, reason = _phase2_gate(latest_dom_dir)
            trace["phase2_gate"] = {"ok": ok, "reason": reason}
            findings_obj = _phase2_findings_obj(latest_dom_dir)

            if not ok:
                html_card = f"<div><h3>{html.escape(dom)}</h3><p><em>No phase2 findings ({html.escape(reason)}).</em></p></div>"
                write_json(card_path, {"html": html_card})
                write_json(latest_path, {"ok": True, "domain": dom, "run_id": run_id, "generated_utc": _now_iso(), "html": html_card})
                trace["ok"] = True
                continue

            findings = _phase2_findings_text(latest_dom_dir)
            if not findings.strip():
                html_card = _fallback_card(dom, findings_obj)
                write_json(card_path, {"html": html_card})
                write_json(latest_path, {"ok": True, "domain": dom, "run_id": run_id, "generated_utc": _now_iso(), "html": html_card})
                trace["ok"] = True
                continue

            system_txt, user_txt = _load_prompt(infra_dir, dom)
            prompt = _build_prompt(system_txt, user_txt, findings)

            prompt_path.write_text(prompt, encoding="utf-8")

            payload: Dict[str, Any] = {
                "model": model,
                "seed": 7,
                "temperature": temperature,
                "n_predict": n_predict,
                "prompt": prompt,
            }
            write_json(req_path, {"url": llm_url, "payload": payload})

            print(f"\n===== PHASE3 SENT [{dom}] =====")
            print(f"temperature={temperature}")
            print(f"prompt_bytes={len(prompt.encode('utf-8'))} sha256={_sha256_text(prompt)}")
            print("--- prompt_full ---")
            print(prompt)

            trace["sent"] = {
                "prompt_sha256": _sha256_text(prompt),
                "prompt_bytes": len(prompt.encode("utf-8")),
                "prompt_full": prompt,
            }

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

            cleaned = _extract_best_div_or_fallback(text or "", dom, findings_obj)
            cleaned_path.write_text(cleaned or "", encoding="utf-8")

            print(f"\n===== PHASE3 RECEIVED [{dom}] =====")
            print(f"http_status={http_status} http_bytes={len(body_bytes)} http_sha256={_sha256_bytes(body_bytes)}")
            print(f"text_bytes={len((text or '').encode('utf-8'))} text_sha256={_sha256_text(text or '')}")
            print("--- response_text_raw ---")
            print(text or "")
            print("--- response_text_cleaned_html ---")
            print(cleaned or "")

            trace["received"] = {
                "http_status": http_status,
                "http_bytes": len(body_bytes),
                "http_sha256": _sha256_bytes(body_bytes),
                "text_bytes": len((text or "").encode("utf-8")),
                "text_sha256": _sha256_text(text or ""),
                "response_text_raw": text or "",
                "response_text_cleaned": cleaned or "",
            }

            write_json(card_path, {"html": cleaned})
            write_json(latest_path, {"ok": True, "domain": dom, "run_id": run_id, "generated_utc": _now_iso(), "html": cleaned})

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

            print(f"\n===== PHASE3 TRACE [{dom}] =====")
            print(json.dumps(trace, ensure_ascii=False, indent=2))

    out["ok"] = not any_fail
    out["ended_at"] = _now_iso()
    out["elapsed_ms"] = int((time.time() - t0) * 1000)

    print("\n===== PHASE3 SUMMARY =====")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out
