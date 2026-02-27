from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Optional, Tuple

from takctl.services.llm.client import LLMClient
from takctl.services.llm.prompt_budget import compute_prompt_budget, apply_prompt_budget


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "ignore")).hexdigest()


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """
    Atomic write within the same directory (write temp + fsync + replace).
    Prevents partial files during concurrent readers, and makes races easier to spot.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}.{int(time.time() * 1000)}")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _sanitize_jsonish_text(raw: str) -> str:
    """
    Make parsing resilient to common llama.cpp / small-instruct quirks:
      - leading/trailing whitespace
      - one or more markdown fences (``` or ```json), sometimes preceded by a stray ``` block
      - extra text before/after JSON (slice to first {/[ and last }/])
    """
    t = (raw or "").strip()
    if not t:
        return t

    # Drop any number of leading fence lines and blank lines.
    # Example seen:
    #   ```\n\n```json\n{...}\n```
    for _ in range(10):  # bounded
        u = t.lstrip()
        if u.startswith("```"):
            lines = u.splitlines()
            lines = lines[1:] if lines else []
            t = "\n".join(lines).strip()
            continue
        # Drop leading blank lines (if any remain)
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

    # Slice to JSON payload
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


def _find_prompt_pack(pack_name: str) -> Tuple[Optional[Path], Optional[Path], dict[str, Any]]:
    """
    Resolve (system.txt, user.txt) for a prompt pack.
    Returns (sys_path, user_path, resolver_meta)
    """
    roots = []
    env_root = (os.environ.get("TAKS_LLM_PROMPT_PACKS_DIR") or "").strip()
    if env_root:
        roots.append(Path(env_root))
    roots += [
        Path("/opt/tak/llm/prompt-packs"),
        Path("/opt/tak/tools/takctl/llm/prompt-packs"),
        Path("/opt/taks/llm-infra/llm/prompt-packs"),
    ]

    tried = []
    for r in roots:
        sys_p = r / pack_name / "system.txt"
        usr_p = r / pack_name / "user.txt"
        tried.append({"root": str(r), "system": str(sys_p), "user": str(usr_p), "ok": sys_p.exists() and usr_p.exists()})
        if sys_p.exists() and usr_p.exists():
            return sys_p, usr_p, {"ok": True, "pack": pack_name, "root": str(r), "tried": tried}

    return None, None, {"ok": False, "pack": pack_name, "tried": tried}


def _json_bytes_pretty(x: Any) -> bytes:
    if isinstance(x, (dict, list)):
        return (json.dumps(x, ensure_ascii=False, indent=2) + "\n").encode("utf-8", "ignore")
    return (str(x) + "\n").encode("utf-8", "ignore")


def run_phase2_findings(
    *,
    ops_brief: dict[str, Any],
    run_id: str,
    domain_id: str,
    pack_name: str,
    out_dir: Path,
    llm_url: str = "",
    max_tokens: int = 900,
    temperature: float = 0.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Phase2: MUST run. Produces:
      - prompt.txt (exact string sent)
      - response.txt (exact raw model output - verbatim choices[0].text)
      - response.http.json (verbatim HTTP JSON body from llama.cpp)
      - trace.json (everything needed to debug)
      - missions_findings.json (parsed JSON or wrapper)

    Returns (findings_obj, trace_obj). Caller writes JSON atomically.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = out_dir / "prompt.txt"
    response_path = out_dir / "response.txt"
    response_http_path = out_dir / "response.http.json"

    t0 = time.time()
    sys_p, usr_p, resolver = _find_prompt_pack(pack_name)

    trace: dict[str, Any] = {
        "contract": {"name": "taks.phase2_trace", "version": 4},
        "ok": False,
        "run_id": run_id,
        "domain_id": domain_id,
        "pack_name": pack_name,
        "resolver": resolver,
        "llm": {
            "url": (llm_url or os.environ.get("TAKS_LLM_URL") or "http://127.0.0.1:8090").strip(),
            "max_tokens": int(max_tokens),
            "temperature": float(temperature),
        },
        "files": {
            "prompt_path": str(prompt_path),
            "response_path": str(response_path),
            "response_http_path": str(response_http_path),
        },
        "timing": {"elapsed_ms": None},
        "parse": {"json_ok": False, "error": None},
        "prompt_budget": None,
        "prompt_budget_trace": None,
        "io": {},
        "http": {},
    }

    if not sys_p or not usr_p:
        _atomic_write_bytes(prompt_path, b"")
        _atomic_write_bytes(response_path, b"")
        _atomic_write_bytes(response_http_path, b"")
        trace["timing"]["elapsed_ms"] = int((time.time() - t0) * 1000)
        findings = {
            "contract": {"name": "taks.ops_findings", "version": 1},
            "ok": False,
            "error": f"prompt_pack_not_found: {pack_name}",
        }
        return findings, trace

    sys_txt = _read_text(sys_p).strip()
    usr_txt = _read_text(usr_p).strip()

    # ---------------------------
    # Prompt budget (C-policy)
    # ---------------------------
    budget = compute_prompt_budget(max_tokens=int(max_tokens))
    max_prompt_bytes = int(budget.get("max_prompt_bytes") or 0) or 16000
    max_string_len = int((os.environ.get("TAKS_LLM_MAX_STRING_LEN") or "").strip() or 800)

    brief_budgeted, budget_trace = apply_prompt_budget(
        ops_brief if isinstance(ops_brief, dict) else {},
        max_prompt_bytes=max_prompt_bytes,
        max_string_len=max_string_len,
    )

    trace["prompt_budget"] = budget
    trace["prompt_budget_trace"] = budget_trace

    data_json = json.dumps(brief_budgeted, ensure_ascii=False, indent=2, sort_keys=True)
    prompt = (
        f"{sys_txt}\n\n"
        f"{usr_txt}\n\n"
        f"## INPUT_OPS_BRIEF_JSON\n"
        f"{data_json}\n"
    )

    prompt_b = prompt.encode("utf-8", "ignore")
    _atomic_write_bytes(prompt_path, prompt_b)

    llm = LLMClient(llm_url=trace["llm"]["url"])
    raw = ""
    http_code = 0
    http_body: Any = None
    http_err: Optional[str] = None

    try:
        raw, http_code, http_body, http_err = llm.completions_debug(prompt, max_tokens=max_tokens, temperature=temperature)
        # Persist verbatim HTTP body too (so UI can prove “model returned X”).
        _atomic_write_bytes(response_http_path, _json_bytes_pretty(http_body))
    except Exception as e:
        trace["ok"] = False
        trace["llm_error"] = f"{type(e).__name__}: {e}"

        _atomic_write_bytes(response_path, b"")
        _atomic_write_bytes(response_http_path, b"")

        trace["timing"]["elapsed_ms"] = int((time.time() - t0) * 1000)
        trace["prompt"] = {
            "sha256": _sha256_bytes(prompt_b),
            "bytes": len(prompt_b),
            "head": prompt[:1200],
            "tail": prompt[-800:] if len(prompt) > 800 else prompt,
        }
        trace["response"] = {"sha256": _sha256_bytes(b""), "bytes": 0, "head": "", "tail": ""}
        trace["http"] = {"code": http_code, "err": http_err, "body_type": type(http_body).__name__ if http_body is not None else None}
        trace["io"] = {
            "response_file_bytes": 0,
            "response_file_sha256": _sha256_bytes(b""),
            "response_write_readback_ok": True,
            "response_write_readback_mismatch": False,
        }

        findings = {
            "contract": {"name": "taks.ops_findings", "version": 1},
            "ok": False,
            "error": "phase2_llm_call_failed",
            "llm_error": trace.get("llm_error"),
            "trace_ref": {"prompt_path": str(prompt_path), "response_path": str(response_path)},
        }
        return findings, trace

    # --- persist RAW model text as-is (no sanitize before persist) ---
    raw_b = (raw or "").encode("utf-8", "ignore")
    _atomic_write_bytes(response_path, raw_b)

    # --- read-back verification (proves post-write corruption / race) ---
    try:
        file_b = response_path.read_bytes()
    except Exception as e:
        file_b = b""
        trace["io"]["response_read_error"] = f"{type(e).__name__}: {e}"

    trace["ok"] = True
    trace["prompt"] = {
        "sha256": _sha256_bytes(prompt_b),
        "bytes": len(prompt_b),
        "head": prompt[:1200],
        "tail": prompt[-800:] if len(prompt) > 800 else prompt,
    }
    trace["response"] = {
        "sha256": _sha256_bytes(raw_b),
        "bytes": len(raw_b),
        "head": (raw or "")[:1200],
        "tail": (raw or "")[-800:] if raw and len(raw) > 800 else (raw or ""),
        "first_16_bytes_hex": raw_b[:16].hex(),
        "last_16_bytes_hex": raw_b[-16:].hex() if len(raw_b) >= 16 else raw_b.hex(),
    }
    trace["http"] = {
        "code": int(http_code),
        "err": http_err,
        "body_type": type(http_body).__name__ if http_body is not None else None,
        "choices_len": len(http_body.get("choices") or []) if isinstance(http_body, dict) else None,
    }
    trace["io"] = {
        "response_file_bytes": len(file_b),
        "response_file_sha256": _sha256_bytes(file_b),
        "response_write_readback_ok": _sha256_bytes(file_b) == _sha256_bytes(raw_b),
        "response_write_readback_mismatch": _sha256_bytes(file_b) != _sha256_bytes(raw_b),
        "response_file_first_16_bytes_hex": file_b[:16].hex(),
        "response_file_last_16_bytes_hex": file_b[-16:].hex() if len(file_b) >= 16 else file_b.hex(),
    }

    findings: dict[str, Any]
    try:
        clean = _sanitize_jsonish_text(raw)
        if not clean:
            raise ValueError("empty_model_output_after_sanitize")
        obj = json.loads(clean)
        if not isinstance(obj, dict):
            raise ValueError("phase2 must return a JSON object")
        obj.setdefault("contract", {"name": "taks.ops_findings", "version": 1})
        obj.setdefault("ok", True)
        findings = obj
        trace["parse"]["json_ok"] = True
    except Exception as e:
        trace["parse"]["json_ok"] = False
        trace["parse"]["error"] = f"{type(e).__name__}: {e}"
        clean = _sanitize_jsonish_text(raw)
        findings = {
            "contract": {"name": "taks.ops_findings", "version": 1},
            "ok": False,
            "error": "phase2_invalid_json",
            "raw_text_head": (raw or "")[:12000],
            "sanitized_text_head": (clean or "")[:12000],
            "trace_ref": {"prompt_path": str(prompt_path), "response_path": str(response_path)},
        }

    trace["timing"]["elapsed_ms"] = int((time.time() - t0) * 1000)
    return findings, trace
