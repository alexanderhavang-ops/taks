from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Tuple

from takctl.services.llm2.llm_client import LlmClient
from takctl.services.llm2.paths import latest_root, runs_root
from takctl.services.llm2.store import write_json


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _read_json(p: Path) -> Any:
    return json.loads(_read_text(p))


def _sha256_text(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8", errors="replace")).hexdigest()


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
    out: List[str] = []
    seen = set()
    for s in vals:
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _fallback_card(dom: str, findings: Dict[str, Any]) -> str:
    title = dom
    important = (str(findings.get("important") or "")).strip()
    newest = (str(findings.get("newest") or "")).strip()
    details = (str(findings.get("details") or "")).strip()

    if important:
        title = important
    elif newest:
        title = newest
    elif details:
        title = details

    summary = ""
    for s in (newest, details):
        s = (s or "").strip()
        if not s or s == title:
            continue
        summary = s
        break

    esc_title = html.escape(title)
    if summary:
        return f"<div><h3>{esc_title}</h3><p>{html.escape(summary)}</p></div>"
    return f"<div><h3>{esc_title}</h3></div>"


def _fallback_detail(dom: str, findings: Dict[str, Any]) -> str:
    important = (str(findings.get("important") or "")).strip()
    newest = (str(findings.get("newest") or "")).strip()
    details = (str(findings.get("details") or "")).strip()

    esc_dom = html.escape(dom)
    parts: List[str] = [f"<div><h3>{esc_dom}</h3>"]
    if important:
        parts.append(f"<p><strong>Important:</strong> {html.escape(important)}</p>")
    if newest:
        parts.append(f"<p><strong>Newest:</strong> {html.escape(newest)}</p>")
    if details:
        parts.append(f"<p><strong>Details:</strong> {html.escape(details)}</p>")
    parts.append("</div>")
    return "".join(parts)


# ---- sanitize/extract ----

_ALLOWED_TAGS = {
    "div", "h3", "p", "ul", "li", "strong", "em", "br",
    "table", "thead", "tbody", "tr", "th", "td",
}
_BAD_TAG_BLOCK_RE = re.compile(r"(?is)<\s*(script|style|iframe|object|embed)\b[^>]*>.*?<\s*/\s*\1\s*>")
_BAD_SINGLE_TAG_RE = re.compile(r"(?is)<\s*(script|style|iframe|object|embed|link|meta)\b[^>]*?/?>")
_ONATTR_RE = re.compile(r'(?is)\s+on[a-zA-Z]+\s*=\s*(".*?"|\'.*?\'|[^\s>]+)')
_JSURL_RE = re.compile(r'(?is)\s+(href|src)\s*=\s*("|\')\s*javascript:.*?\2')
_STYLE_ATTR_RE = re.compile(r'(?is)\s+style\s*=\s*(".*?"|\'.*?\'|[^\s>]+)')
_JUNK_TAGS_RE = re.compile(r"(?is)</?\s*(commit_msg|commit_after)\b[^>]*>")
_DIV_RE = re.compile(r"(?is)<div\b[^>]*>.*?</div>")
_PLACEHOLDER_RE = re.compile(r"(?is)\.\.\.|<h3>\s*\.\.\s*</h3>|<p>\s*\.\.\s*</p>|<li>\s*\.\.\s*</li>")


def _strip_disallowed_tags_keep_text(s: str) -> str:
    def repl(m: re.Match) -> str:
        tag = (m.group(1) or "").lower()
        return m.group(0) if tag in _ALLOWED_TAGS else ""
    return re.sub(r"(?is)</?\s*([a-zA-Z0-9:_-]+)\b[^>]*>", repl, s)


def _strip_all_attrs_except_data(s: str) -> str:
    def repl(m: re.Match) -> str:
        full = m.group(0)
        tag = (m.group(1) or "")
        if full.startswith("</"):
            return f"</{tag}>"
        attrs = m.group(2) or ""
        keep = []
        for am in re.finditer(r'(?is)\s+([a-zA-Z0-9:_-]+)\s*=\s*(".*?"|\'.*?\'|[^\s>]+)', attrs):
            name = (am.group(1) or "").lower()
            val = am.group(2) or ""
            if name.startswith("data-"):
                keep.append(f' {name}={val}')
        return f"<{tag}{''.join(keep)}>"
    return re.sub(r"(?is)<\s*([a-zA-Z0-9:_-]+)\b([^>]*)>", repl, s)


def _sanitize_html_fragment(frag: str) -> str:
    frag = (frag or "").strip()
    frag = _BAD_TAG_BLOCK_RE.sub("", frag)
    frag = _BAD_SINGLE_TAG_RE.sub("", frag)
    frag = _JUNK_TAGS_RE.sub("", frag)
    frag = _ONATTR_RE.sub("", frag)
    frag = _JSURL_RE.sub("", frag)
    frag = _STYLE_ATTR_RE.sub("", frag)
    frag = _strip_disallowed_tags_keep_text(frag)
    frag = _strip_all_attrs_except_data(frag)
    frag = re.sub(r"\n{4,}", "\n\n", frag).strip()
    return frag


def _looks_like_dump_html(html_card: str, *, max_len: int) -> bool:
    t = (html_card or "").strip()
    if not t:
        return True
    if len(t) > max_len:
        return True
    if t.count("&quot;") >= 8:
        return True
    if "&quot;:" in t:
        return True
    if '{"' in t or '":' in t:
        return True
    return False


def _extract_best_div_or_fallback(raw: str, dom: str, findings: Dict[str, Any], *, kind: str) -> str:
    t = (raw or "").strip()
    vals = _findings_values(findings)

    m = re.search(r"(?is)```html\s*(.*?)\s*```", t)
    if m and (m.group(1) or "").strip():
        t = (m.group(1) or "").strip()

    divs = _DIV_RE.findall(t)

    def score(div: str) -> int:
        d = div or ""
        if _PLACEHOLDER_RE.search(d):
            return -9999
        s = 0
        for v in vals:
            if not v:
                continue
            if v in d:
                s += 1000
            else:
                piece = v[:40]
                if piece and piece in d:
                    s += 100
        if "OUTPUT RULES" in d or "Start immediately" in d or "Output exactly" in d:
            s -= 800
        return s

    best = None
    best_score = -10**9
    for d in divs:
        sc = score(d)
        if sc > best_score:
            best = d
            best_score = sc

    cleaned = ""
    if best:
        cleaned = _sanitize_html_fragment(best).strip()

    if cleaned and not cleaned.lower().startswith("<div"):
        cleaned = "<div>" + cleaned + "</div>"
    if cleaned and not cleaned.lower().endswith("</div>"):
        cleaned = cleaned + "</div>"

    if cleaned:
        if _PLACEHOLDER_RE.search(cleaned):
            cleaned = ""
        else:
            if kind == "card":
                if _looks_like_dump_html(cleaned, max_len=1600):
                    cleaned = ""
            else:
                if _looks_like_dump_html(cleaned, max_len=20000):
                    cleaned = ""

    if cleaned:
        return cleaned

    return _fallback_card(dom, findings) if kind == "card" else _fallback_detail(dom, findings)


def _discover_domains() -> List[str]:
    root = latest_root()
    if not root.exists():
        return []
    doms = [p.name for p in root.iterdir() if p.is_dir()]
    doms = [d for d in doms if d]
    if "_summary" in doms:
        doms = ["_summary"] + [d for d in doms if d != "_summary"]
    return sorted([d for d in doms if d != "_summary"]) and (["_summary"] + sorted([d for d in doms if d != "_summary"])) or doms


def _load_prompt_pair(infra_dir: Path, dom: str, kind: str) -> Tuple[str, str]:
    base = infra_dir / "domains" / dom / "prompts" / "phase3"
    sys_p = base / f"{kind}_system.txt"
    usr_p = base / f"{kind}_user.txt"

    system_txt = _read_text(sys_p).strip()
    user_txt = _read_text(usr_p).strip()

    if not system_txt:
        system_txt = (
            "You generate operator-facing HTML for a tactical dashboard.\n"
            "OUTPUT MUST BE HTML ONLY.\n"
            "- No JSON.\n"
            "- No markdown fences.\n\n"
            "Safety:\n"
            "- Do NOT use <script>, <style>, <iframe>, <object>, <embed>, <link>, <meta>.\n"
            "- Do NOT use inline event handlers.\n"
            "- Do NOT use javascript: URLs.\n"
            "- Do NOT use style= attributes.\n\n"
            "Factuality:\n"
            "- Do not invent facts.\n"
        )

    if not user_txt:
        if kind == "card":
            user_txt = (
                f'Create a compact operator-facing HTML card for domain "{dom}".\n'
                "Make it scannable: 1 headline + up to 3 bullets.\n"
                "No long paragraphs.\n"
            )
        else:
            user_txt = (
                f'Create a detailed operator-facing HTML view for domain "{dom}".\n'
                "Use sections and structure. If helpful, include a small table.\n"
                "Prefer structure over verbosity.\n"
            )

    return system_txt, user_txt


def _build_prompt(system_txt: str, user_txt: str, findings_json: str, *, kind: str) -> str:
    parts: List[str] = []
    parts.append(system_txt.strip())
    parts.append("")
    parts.append(user_txt.strip())
    parts.append("")
    parts.append("Input is Phase2 findings JSON (evidence).")
    parts.append("")
    parts.append("OUTPUT RULES (STRICT):")
    parts.append("- Start immediately with '<div>' (first non-whitespace characters).")
    parts.append("- Output exactly ONE HTML block: a single <div> ... </div>.")
    if kind == "card":
        parts.append("- Keep it very compact (dashboard card).")
        parts.append("- Prefer: one <h3> and optionally ONE short <p>.")
        parts.append("- Use a <ul> only if truly necessary, with max 2 <li>.")
        parts.append("- Each <li> must be short and scannable.")
        parts.append("- Do NOT write long paragraphs.")
        parts.append("- The card should fit a compact overview grid.")
    else:
        parts.append("- This is a detail view (may be longer than the card).")
        parts.append("- Prefer structure and sections; you may use a table.")
    parts.append("- Allowed tags: div, h3, p, ul, li, strong, em, br, table, thead, tbody, tr, th, td.")
    parts.append("- Do NOT include any prose outside the single <div>.")
    parts.append("- Do NOT output placeholders like '..' or '...'.")
    parts.append("- Do not invent facts.")
    parts.append("- Do NOT use style= attributes.")
    parts.append("")
    parts.append("## INPUT_FINDINGS_JSON")
    parts.append(findings_json.strip())
    parts.append("")
    return "\n".join(parts).strip() + "\n"


def run_phase3(*, run_id: str) -> Dict[str, Any]:
    started = _now_iso()
    t0 = time.time()

    infra_dir = Path(os.environ.get("TAKCTL_LLM2_INFRA_DIR", "/opt/tak/tools/takctl/llm-infra"))
    phase3_mode = (os.environ.get("TAKCTL_LLM2_PHASE3_MODE", "fallback") or "fallback").strip().lower()

    domains = _discover_domains()

    out: Dict[str, Any] = {
        "ok": True,
        "run_id": run_id,
        "phase": "phase3",
        "started_at": started,
        "domains": domains,
        "phase3_mode": phase3_mode,
    }

    any_fail = False

    (runs_root() / run_id).mkdir(parents=True, exist_ok=True)
    latest_root().mkdir(parents=True, exist_ok=True)

    client = LlmClient()

    for dom in domains:
        dom_t0 = time.time()
        dom_started = _now_iso()

        latest_dom_dir = latest_root() / dom
        run_dom_dir = runs_root() / run_id / dom / "phase3"
        run_dom_dir.mkdir(parents=True, exist_ok=True)

        latest_phase3_dir = latest_dom_dir / "phase3"
        latest_phase3_dir.mkdir(parents=True, exist_ok=True)

        # artifacts
        card_path = run_dom_dir / "card.json"
        detail_path = run_dom_dir / "detail.json"
        latest_card_path = latest_phase3_dir / "card.json"
        latest_detail_path = latest_phase3_dir / "detail.json"
        latest_path = latest_phase3_dir / "latest.json"
        trace_run_path = run_dom_dir / "trace.json"
        trace_latest_path = latest_phase3_dir / "trace.json"

        prompt_card_path = run_dom_dir / "prompt.card.txt"
        prompt_detail_path = run_dom_dir / "prompt.detail.txt"
        resp_card_path = run_dom_dir / "response.card.txt"
        resp_detail_path = run_dom_dir / "response.detail.txt"
        cleaned_card_path = run_dom_dir / "cleaned.card.html"
        cleaned_detail_path = run_dom_dir / "cleaned.detail.html"

        trace: Dict[str, Any] = {
            "phase": "phase3",
            "domain": dom,
            "run_id": run_id,
            "started_at": dom_started,
            "ok": False,
            "phase2_gate": None,
            "phase3_mode": phase3_mode,
            "llm": {
                "provider": getattr(client, "provider", None),
                "model": (client.bedrock_model_id if getattr(client, "provider", "") == "bedrock" else client.model),
                "env_path": getattr(client, "env_path", None),
            },
            "card": {"ok": False, "error": None},
            "detail": {"ok": False, "error": None},
            "files": {
                "card_path": str(card_path),
                "detail_path": str(detail_path),
                "latest_card_path": str(latest_card_path),
                "latest_detail_path": str(latest_detail_path),
                "prompt_card_path": str(prompt_card_path),
                "prompt_detail_path": str(prompt_detail_path),
                "resp_card_path": str(resp_card_path),
                "resp_detail_path": str(resp_detail_path),
                "cleaned_card_path": str(cleaned_card_path),
                "cleaned_detail_path": str(cleaned_detail_path),
                "trace_run_path": str(trace_run_path),
                "trace_latest_path": str(trace_latest_path),
            },
        }

        try:
            ok_gate, reason = _phase2_gate(latest_dom_dir)
            trace["phase2_gate"] = {"ok": ok_gate, "reason": reason}
            findings_obj = _phase2_findings_obj(latest_dom_dir)
            findings_txt = _phase2_findings_text(latest_dom_dir)

            if not ok_gate:
                card_html = f"<div><h3>{html.escape(dom)}</h3><p><em>No phase2 findings ({html.escape(reason)}).</em></p></div>"
                detail_html = card_html
                write_json(card_path, {"html": card_html})
                write_json(detail_path, {"html": detail_html})
                write_json(latest_card_path, {"html": card_html})
                write_json(latest_detail_path, {"html": detail_html})
                write_json(latest_path, {"ok": True, "domain": dom, "run_id": run_id, "generated_utc": _now_iso()})
                trace["card"]["ok"] = True
                trace["detail"]["ok"] = True
                trace["ok"] = True
                continue

            if not findings_txt.strip():
                card_html = _fallback_card(dom, findings_obj)
                detail_html = _fallback_detail(dom, findings_obj)
                write_json(card_path, {"html": card_html})
                write_json(detail_path, {"html": detail_html})
                write_json(latest_card_path, {"html": card_html})
                write_json(latest_detail_path, {"html": detail_html})
                write_json(latest_path, {"ok": True, "domain": dom, "run_id": run_id, "generated_utc": _now_iso()})
                trace["card"]["ok"] = True
                trace["detail"]["ok"] = True
                trace["ok"] = True
                continue

            if phase3_mode != "llm":
                card_html = _fallback_card(dom, findings_obj)
                detail_html = _fallback_detail(dom, findings_obj)
                write_json(card_path, {"html": card_html})
                write_json(detail_path, {"html": detail_html})
                write_json(latest_card_path, {"html": card_html})
                write_json(latest_detail_path, {"html": detail_html})
                write_json(latest_path, {"ok": True, "domain": dom, "run_id": run_id, "generated_utc": _now_iso()})
                trace["card"]["ok"] = True
                trace["detail"]["ok"] = True
                trace["ok"] = True
                continue

            # LLM mode: two calls (card + detail)
            temp = float(os.environ.get("TAKCTL_LLM_TEMPERATURE", "0.2"))

            sys_card, usr_card = _load_prompt_pair(infra_dir, dom, "card")
            prompt_card = _build_prompt(sys_card, usr_card, findings_txt, kind="card")
            prompt_card_path.write_text(prompt_card, encoding="utf-8")
            trace["card"]["prompt_sha256"] = _sha256_text(prompt_card)
            trace["card"]["prompt_bytes"] = len(prompt_card.encode("utf-8"))

            r1 = client.complete_text(prompt=prompt_card, temperature=temp, max_tokens=300, seed=7)
            resp_card_path.write_text(r1.get("text") or "", encoding="utf-8")
            if not r1.get("ok"):
                raise RuntimeError(f"phase3_card_llm_failed:{r1.get('error')}")
            card_clean = _extract_best_div_or_fallback(r1.get("text") or "", dom, findings_obj, kind="card")
            cleaned_card_path.write_text(card_clean, encoding="utf-8")

            sys_det, usr_det = _load_prompt_pair(infra_dir, dom, "detail")
            prompt_det = _build_prompt(sys_det, usr_det, findings_txt, kind="detail")
            prompt_detail_path.write_text(prompt_det, encoding="utf-8")
            trace["detail"]["prompt_sha256"] = _sha256_text(prompt_det)
            trace["detail"]["prompt_bytes"] = len(prompt_det.encode("utf-8"))

            r2 = client.complete_text(prompt=prompt_det, temperature=temp, max_tokens=1800, seed=7)
            resp_detail_path.write_text(r2.get("text") or "", encoding="utf-8")
            if not r2.get("ok"):
                raise RuntimeError(f"phase3_detail_llm_failed:{r2.get('error')}")
            det_clean = _extract_best_div_or_fallback(r2.get("text") or "", dom, findings_obj, kind="detail")
            cleaned_detail_path.write_text(det_clean, encoding="utf-8")

            write_json(card_path, {"html": card_clean})
            write_json(detail_path, {"html": det_clean})
            write_json(latest_card_path, {"html": card_clean})
            write_json(latest_detail_path, {"html": det_clean})
            write_json(latest_path, {"ok": True, "domain": dom, "run_id": run_id, "generated_utc": _now_iso()})

            trace["card"]["ok"] = True
            trace["detail"]["ok"] = True
            trace["ok"] = True

        except Exception as e:
            any_fail = True
            trace["ok"] = False
            trace["error"] = f"{type(e).__name__}: {e}"
            trace["traceback"] = traceback.format_exc()
            trace["card"]["error"] = trace["error"]
            trace["detail"]["error"] = trace["error"]

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
