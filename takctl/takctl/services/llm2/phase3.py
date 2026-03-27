from __future__ import annotations

import hashlib
import json
import os
import re
import time
import traceback
from pathlib import Path
from takctl.config import load_config
from typing import Any, Dict, List, Tuple

from takctl.services.llm2.domain_config import (
    discover_enabled_domains,
    load_domain_config,
    phase_enabled,
)
from takctl.services.llm2.llm_client import LlmClient
from takctl.services.llm2.paths import latest_root, runs_root
from takctl.config_store import load_runtime_config_view
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


def _runtime_language() -> str:
    try:
        cfg = load_runtime_config_view()
        lang = str(cfg.get("language", "sv")).strip().lower()
        return lang or "sv"
    except Exception:
        return "sv"


def _load_prompt_pair(infra_dir: Path, dom: str, kind: str) -> Tuple[str, str]:
    base = infra_dir / "domains" / dom / "prompts" / "phase3"
    lang = _runtime_language()

    candidates = [
        (base / lang / f"{kind}_system.txt", base / lang / f"{kind}_user.txt"),
        (base / "en" / f"{kind}_system.txt", base / "en" / f"{kind}_user.txt"),
        (base / f"{kind}_system.txt", base / f"{kind}_user.txt"),
    ]

    for sys_p, usr_p in candidates:
        system_txt = _read_text(sys_p).strip()
        user_txt = _read_text(usr_p).strip()
        if system_txt and user_txt:
            return system_txt, user_txt

    raise RuntimeError(f"missing prompt files for domain={dom} kind={kind} lang={lang}: {candidates}")


def _build_prompt(system_txt: str, user_txt: str, findings_json: str) -> str:
    return (
        system_txt.strip()
        + "\n\n"
        + user_txt.strip()
        + "\n\n## INPUT_FINDINGS_JSON\n"
        + findings_json.strip()
        + "\n"
    )


_BAD_TAG_BLOCK_RE = re.compile(
    r"(?is)<\s*(script|style|iframe|object|embed|foreignObject)\b[^>]*>.*?<\s*/\s*\1\s*>"
)
_BAD_SINGLE_TAG_RE = re.compile(
    r"(?is)<\s*(script|style|iframe|object|embed|link|meta)\b[^>]*?/?>"
)
_ONATTR_RE = re.compile(r'(?is)\s+on[a-zA-Z:_-]+\s*=\s*(".*?"|\'.*?\'|[^\s>]+)')
_JSURL_DQ_RE = re.compile(r'(?is)\s+(href|src|xlink:href)\s*=\s*"[^"]*javascript:[^"]*"')
_JSURL_SQ_RE = re.compile(r"(?is)\s+(href|src|xlink:href)\s*=\s*'[^']*javascript:[^']*'")
_JSURL_BARE_RE = re.compile(r"(?is)\s+(href|src|xlink:href)\s*=\s*javascript:[^\s>]+")
_JUNK_TAGS_RE = re.compile(r"(?is)</?\s*(commit_msg|commit_after)\b[^>]*>")
_PLACEHOLDER_RE = re.compile(
    r"(?is)\.\.\.|<h3>\s*\.\.\s*</h3>|<p>\s*\.\.\s*</p>|<li>\s*\.\.\s*</li>"
)


def _basic_safe_cleanup(frag: str) -> str:
    frag = (frag or "").strip()
    frag = _BAD_TAG_BLOCK_RE.sub("", frag)
    frag = _BAD_SINGLE_TAG_RE.sub("", frag)
    frag = _JUNK_TAGS_RE.sub("", frag)
    frag = _ONATTR_RE.sub("", frag)
    frag = _JSURL_DQ_RE.sub("", frag)
    frag = _JSURL_SQ_RE.sub("", frag)
    frag = _JSURL_BARE_RE.sub("", frag)
    frag = re.sub(r"\n{4,}", "\n\n", frag).strip()
    return frag


def _extract_outer_div_block(text: str) -> str:
    s = text or ""

    m = re.search(r"(?is)<div\b[^>]*>", s)
    if not m:
        return ""

    start = m.start()
    pos = m.end()
    depth = 1
    tag_re = re.compile(r"(?is)</?div\b[^>]*>")

    while True:
        tm = tag_re.search(s, pos)
        if not tm:
            return s[start:]
        token = tm.group(0).lower()
        if token.startswith("</div"):
            depth -= 1
            if depth == 0:
                return s[start:tm.end()]
        else:
            depth += 1
        pos = tm.end()


def _extract_best_div(raw: str) -> str:
    t = (raw or "").strip()

    m = re.search(r"(?is)```html\s*(.*?)\s*```", t)
    if m and (m.group(1) or "").strip():
        t = (m.group(1) or "").strip()

    best = _extract_outer_div_block(t) or t
    cleaned = _basic_safe_cleanup(best).strip()

    if cleaned and not re.match(r"(?is)^<div\b", cleaned):
        cleaned = f"<div>{cleaned}</div>"
    if cleaned and not re.search(r"(?is)</div>\s*$", cleaned):
        cleaned = cleaned + "</div>"

    if cleaned and not _PLACEHOLDER_RE.search(cleaned):
        return cleaned

    raise RuntimeError("no_valid_html_div_found")


def _selected_domains(infra_dir: Path, domain: str | None = None) -> List[str]:
    requested = (domain or "").strip()
    all_domains = discover_enabled_domains(infra_dir)

    if not requested or requested.lower() == "all":
        return all_domains

    if requested not in all_domains:
        cfg_path = infra_dir / "domains" / requested / "config.json"
        if not cfg_path.exists():
            raise RuntimeError(f"unknown_or_disabled_domain:{requested}")
        cfg = load_domain_config(infra_dir, requested)
        if cfg.get("enabled", True) is False:
            raise RuntimeError(f"domain_disabled:{requested}")
        return [requested]

    return [requested]


def run_phase3(*, run_id: str, domain: str | None = None) -> Dict[str, Any]:
    started = _now_iso()
    t0 = time.time()

    cfg0 = load_config()
    infra_dir = Path(cfg0.llm_infra_dir)
    phase3_mode = (cfg0.llm_phase3_mode or "llm").strip().lower()
    temperature = float(cfg0.llm_temperature)
    n_predict = int(cfg0.llm_n_predict)

    domains = _selected_domains(infra_dir, domain=domain)

    out: Dict[str, Any] = {
        "ok": True,
        "run_id": run_id,
        "phase": "phase3",
        "started_at": started,
        "domains": domains,
        "phase3_mode": phase3_mode,
        "n_predict": n_predict,
        "domain": domains[0] if len(domains) == 1 else "all",
    }

    any_fail = False

    (runs_root() / run_id).mkdir(parents=True, exist_ok=True)
    latest_root().mkdir(parents=True, exist_ok=True)

    client = LlmClient()

    for dom in domains:
        cfg = load_domain_config(infra_dir, dom)

        if not phase_enabled(cfg, "phase3"):
            print(f"\n===== PHASE3 SKIP [{dom}] reason=phase3_disabled_in_config =====")
            continue

        dom_t0 = time.time()
        dom_started = _now_iso()

        latest_dom_dir = latest_root() / dom
        run_dom_dir = runs_root() / run_id / dom / "phase3"
        run_dom_dir.mkdir(parents=True, exist_ok=True)

        latest_phase3_dir = latest_dom_dir / "phase3"
        latest_phase3_dir.mkdir(parents=True, exist_ok=True)

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
            "domain_mode": str(cfg.get("mode") or ""),
            "phase3_enabled": phase_enabled(cfg, "phase3"),
            "llm": {
                "provider": getattr(client, "provider", None),
                "model": (
                    client.bedrock_model_id
                    if getattr(client, "provider", "") == "bedrock"
                    else client.model
                ),
                "env_path": getattr(client, "env_path", None),
                "n_predict": n_predict,
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

            findings_txt = _phase2_findings_text(latest_dom_dir)

            if not ok_gate:
                raise RuntimeError(f"phase2_not_ready:{reason}")
            if not findings_txt.strip():
                raise RuntimeError("phase2_findings_empty")
            if phase3_mode != "llm":
                raise RuntimeError(f"unsupported_phase3_mode:{phase3_mode}")

            sys_card, usr_card = _load_prompt_pair(infra_dir, dom, "card")
            prompt_card = _build_prompt(sys_card, usr_card, findings_txt)
            prompt_card_path.write_text(prompt_card, encoding="utf-8")
            trace["card"]["prompt_sha256"] = _sha256_text(prompt_card)
            trace["card"]["prompt_bytes"] = len(prompt_card.encode("utf-8"))
            trace["card"]["prompt_full"] = prompt_card

            print(f"\n===== PHASE3 SENT [{dom}:card] =====")
            print(f"temperature={temperature}")
            print(f"n_predict={n_predict}")
            print(f"prompt_bytes={len(prompt_card.encode('utf-8'))} sha256={_sha256_text(prompt_card)}")
            print("--- prompt_full ---")
            print(prompt_card)

            r1 = client.complete_text(
                prompt=prompt_card,
                temperature=temperature,
                max_tokens=n_predict,
                seed=7,
            
                        purpose=f"phase3:{dom}:card",
                    )
            card_raw = r1.get("text") or ""
            resp_card_path.write_text(card_raw, encoding="utf-8")

            print(f"\n===== PHASE3 RECEIVED [{dom}:card] =====")
            print(f"http_status={r1.get('http_status')} bytes={r1.get('body_bytes')}")
            print(f"text_bytes={len(card_raw.encode('utf-8'))} text_sha256={_sha256_text(card_raw)}")
            print("--- response_text_raw ---")
            print(card_raw)

            trace["card"]["received"] = {
                "http_status": r1.get("http_status"),
                "body_bytes": r1.get("body_bytes"),
                "text_bytes": len(card_raw.encode("utf-8")),
                "text_sha256": _sha256_text(card_raw),
                "response_text_raw": card_raw,
                "provider": r1.get("provider"),
                "url": r1.get("url"),
                "model": r1.get("model"),
                "error": r1.get("error"),
            }

            if not r1.get("ok"):
                raise RuntimeError(f"phase3_card_llm_failed:{r1.get('error')}")

            card_clean = _extract_best_div(card_raw)
            cleaned_card_path.write_text(card_clean, encoding="utf-8")

            sys_det, usr_det = _load_prompt_pair(infra_dir, dom, "detail")
            prompt_det = _build_prompt(sys_det, usr_det, findings_txt)
            prompt_detail_path.write_text(prompt_det, encoding="utf-8")
            trace["detail"]["prompt_sha256"] = _sha256_text(prompt_det)
            trace["detail"]["prompt_bytes"] = len(prompt_det.encode("utf-8"))
            trace["detail"]["prompt_full"] = prompt_det

            print(f"\n===== PHASE3 SENT [{dom}:detail] =====")
            print(f"temperature={temperature}")
            print(f"n_predict={n_predict}")
            print(f"prompt_bytes={len(prompt_det.encode('utf-8'))} sha256={_sha256_text(prompt_det)}")
            print("--- prompt_full ---")
            print(prompt_det)

            r2 = client.complete_text(
                prompt=prompt_det,
                temperature=temperature,
                max_tokens=n_predict,
                seed=7,
            
                        purpose=f"phase3:{dom}:detail",
                    )
            det_raw = r2.get("text") or ""
            resp_detail_path.write_text(det_raw, encoding="utf-8")

            print(f"\n===== PHASE3 RECEIVED [{dom}:detail] =====")
            print(f"http_status={r2.get('http_status')} bytes={r2.get('body_bytes')}")
            print(f"text_bytes={len(det_raw.encode('utf-8'))} text_sha256={_sha256_text(det_raw)}")
            print("--- response_text_raw ---")
            print(det_raw)

            trace["detail"]["received"] = {
                "http_status": r2.get("http_status"),
                "body_bytes": r2.get("body_bytes"),
                "text_bytes": len(det_raw.encode("utf-8")),
                "text_sha256": _sha256_text(det_raw),
                "response_text_raw": det_raw,
                "provider": r2.get("provider"),
                "url": r2.get("url"),
                "model": r2.get("model"),
                "error": r2.get("error"),
            }

            if not r2.get("ok"):
                raise RuntimeError(f"phase3_detail_llm_failed:{r2.get('error')}")

            det_clean = _extract_best_div(det_raw)
            cleaned_detail_path.write_text(det_clean, encoding="utf-8")

            write_json(card_path, {"html": card_clean})
            write_json(detail_path, {"html": det_clean})
            write_json(latest_card_path, {"html": card_clean})
            write_json(latest_detail_path, {"html": det_clean})
            write_json(
                latest_path,
                {"ok": True, "domain": dom, "run_id": run_id, "generated_utc": _now_iso()},
            )

            trace["card"]["ok"] = True
            trace["detail"]["ok"] = True
            trace["ok"] = True

        except Exception as e:
            any_fail = True
            trace["ok"] = False
            trace["error"] = f"{type(e).__name__}: {e}"
            trace["traceback"] = traceback.format_exc()
            write_json(
                latest_path,
                {"ok": False, "domain": dom, "run_id": run_id, "generated_utc": _now_iso()},
            )

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

