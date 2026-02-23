from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List, Tuple


def _get_int_env(name: str, default: int) -> int:
    try:
        v = int((os.environ.get(name) or "").strip() or default)
        return v
    except Exception:
        return default


def compute_prompt_budget(*, max_tokens: int) -> dict[str, Any]:
    """
    Compute a conservative prompt budget in BYTES to avoid llama.cpp n_ctx cliff.

    llama.cpp: n_ctx ~= prompt_tokens + generated_tokens

    We approximate tokens ~= bytes / bytes_per_token.
    This is imperfect, but good enough to keep us away from the edge.

    Defaults:
      ctx_tokens: 4096 (llama-server -c 4096)
      safety_tokens: 256 (headroom for formatting + variance)
      bytes_per_token: 4 (English-ish; conservative-ish)
    Env overrides:
      TAKS_LLM_CTX_TOKENS (or TAKS_LLM_CTX)
      TAKS_LLM_SAFETY_TOKENS
      TAKS_LLM_BYTES_PER_TOKEN
      TAKS_LLM_MAX_PROMPT_BYTES (hard override)
    """
    ctx_tokens = _get_int_env("TAKS_LLM_CTX_TOKENS", _get_int_env("TAKS_LLM_CTX", 4096))
    safety_tokens = _get_int_env("TAKS_LLM_SAFETY_TOKENS", 256)
    bytes_per_token = _get_int_env("TAKS_LLM_BYTES_PER_TOKEN", 4)

    hard = (os.environ.get("TAKS_LLM_MAX_PROMPT_BYTES") or "").strip()
    if hard:
        try:
            hard_i = int(hard)
            return {
                "ctx_tokens": int(ctx_tokens),
                "max_tokens": int(max_tokens),
                "safety_tokens": int(safety_tokens),
                "bytes_per_token": int(bytes_per_token),
                "max_prompt_bytes": int(hard_i),
                "policy": "hard_override",
            }
        except Exception:
            pass

    # tokens available for prompt
    prompt_tokens = max(64, int(ctx_tokens) - int(max_tokens) - int(safety_tokens))
    max_prompt_bytes = max(1024, int(prompt_tokens) * int(bytes_per_token))

    return {
        "ctx_tokens": int(ctx_tokens),
        "max_tokens": int(max_tokens),
        "safety_tokens": int(safety_tokens),
        "bytes_per_token": int(bytes_per_token),
        "max_prompt_bytes": int(max_prompt_bytes),
        "policy": "derived",
    }


def _json_bytes(obj: Any) -> int:
    try:
        return len(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8", "ignore"))
    except Exception:
        try:
            return len(str(obj).encode("utf-8", "ignore"))
        except Exception:
            return 0


def _truncate_strings(obj: Any, *, max_str: int, trace: dict[str, Any], path: str = "") -> Any:
    """
    Truncate very long strings inside obj (recursive). Keeps determinism.
    """
    if isinstance(obj, str):
        if max_str > 0 and len(obj) > max_str:
            trace.setdefault("string_truncations", 0)
            trace["string_truncations"] += 1
            return obj[:max_str] + "…"
        return obj

    if isinstance(obj, list):
        out = []
        for i, v in enumerate(obj):
            out.append(_truncate_strings(v, max_str=max_str, trace=trace, path=f"{path}[{i}]"))
        return out

    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            kk = str(k)
            out[kk] = _truncate_strings(v, max_str=max_str, trace=trace, path=f"{path}.{kk}" if path else kk)
        return out

    return obj


def _weights_from_ops_brief(ops_brief: dict[str, Any]) -> dict[str, int]:
    """
    Priority weights per evidence list.
    Higher weight = allowed to take more of the prompt.
    You can pass:
      ops_brief["prompt_policy"]["evidence_weights"] = {"changes_head": 5, ...}

    Defaults are sane for tactical ops.
    """
    defaults = {
        "changes_head": 5,
        "missions_head": 4,
        "invitations_head": 3,
        # if more evidence lists appear later, give them low default weight
    }
    try:
        pp = ops_brief.get("prompt_policy") or {}
        w = pp.get("evidence_weights") or {}
        if isinstance(w, dict) and w:
            out = defaults.copy()
            for k, v in w.items():
                try:
                    out[str(k)] = int(v)
                except Exception:
                    out[str(k)] = out.get(str(k), 1)
            return out
    except Exception:
        pass
    return defaults


def apply_prompt_budget(
    ops_brief: dict[str, Any],
    *,
    max_prompt_bytes: int,
    max_string_len: int = 800,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    C-policy:
      1) Allocate % budgets by priority WEIGHTS across evidence lists
      2) Trim evidence rows deterministically to fit overall budget
      3) Fallback pass: global trim (lowest weight first) if still too big

    Returns (ops_brief_budgeted, budget_trace)
    """
    trace: dict[str, Any] = {
        "contract": {"name": "taks.prompt_budget_trace", "version": 1},
        "max_prompt_bytes": int(max_prompt_bytes),
        "max_string_len": int(max_string_len),
        "before_bytes": None,
        "after_bytes": None,
        "sections": [],
        "fallback_drops": [],
    }

    # Deep copy so we never mutate caller state
    brief = copy.deepcopy(ops_brief if isinstance(ops_brief, dict) else {})

    # Ensure stable shape
    brief.setdefault("prompt_policy", {})
    brief["prompt_policy"].setdefault("applied", True)
    brief["prompt_policy"].setdefault("max_prompt_bytes", int(max_prompt_bytes))

    # Always trim pathological strings first (cheap + helps a lot if any big text sneaks in)
    brief = _truncate_strings(brief, max_str=max_string_len, trace=trace)

    before = _json_bytes(brief)
    trace["before_bytes"] = int(before)

    if before <= max_prompt_bytes:
        trace["after_bytes"] = int(before)
        return brief, trace

    evidence = brief.get("evidence")
    if not isinstance(evidence, dict):
        # nothing structured to trim; return as-is
        trace["after_bytes"] = int(before)
        return brief, trace

    # Identify evidence lists
    keys: List[str] = []
    for k, v in evidence.items():
        if isinstance(v, list):
            keys.append(str(k))

    if not keys:
        trace["after_bytes"] = int(before)
        return brief, trace

    weights = _weights_from_ops_brief(brief)
    # For unknown keys, default weight=1
    wsum = 0
    for k in keys:
        wsum += int(weights.get(k, 1))

    # Compute overhead bytes excluding evidence lists content (approx by clearing lists)
    evidence_shadow = copy.deepcopy(evidence)
    for k in keys:
        evidence_shadow[k] = []
    base_shadow = copy.deepcopy(brief)
    base_shadow["evidence"] = evidence_shadow
    overhead = _json_bytes(base_shadow)

    # If overhead itself is too big, we can’t really help here.
    if overhead >= max_prompt_bytes:
        # Still record something useful
        trace["sections"].append({"key": "__overhead__", "overhead_bytes": int(overhead), "note": "overhead >= budget"})
        trace["after_bytes"] = int(before)
        return brief, trace

    remaining = max_prompt_bytes - overhead

    # 1) Weighted per-section budgets, then trim each list to its budget.
    for k in keys:
        w = int(weights.get(k, 1))
        section_budget = max(128, int(remaining * (w / max(1, wsum))))

        lst = evidence.get(k)
        if not isinstance(lst, list):
            continue

        # binary-ish trim: drop tail until under section_budget
        kept = len(lst)
        dropped = 0

        # Start from full list and shrink
        lo = 0
        hi = len(lst)
        best = 0

        def section_bytes(n: int) -> int:
            ev = copy.deepcopy(evidence_shadow)
            ev[k] = lst[:n]
            tmp = copy.deepcopy(base_shadow)
            tmp["evidence"] = ev
            return _json_bytes(tmp) - overhead

        # Quick accept
        if section_bytes(hi) <= section_budget:
            best = hi
        else:
            # Binary search best n
            lo, hi = 0, hi
            while lo <= hi:
                mid = (lo + hi) // 2
                b = section_bytes(mid)
                if b <= section_budget:
                    best = mid
                    lo = mid + 1
                else:
                    hi = mid - 1

        kept = best
        dropped = max(0, len(lst) - kept)
        evidence[k] = lst[:kept]

        trace["sections"].append({
            "key": k,
            "weight": w,
            "budget_bytes": int(section_budget),
            "kept": int(kept),
            "dropped": int(dropped),
        })

    brief["evidence"] = evidence

    # 2) Global fallback: if still too big, drop more from lowest weight first.
    after1 = _json_bytes(brief)
    if after1 > max_prompt_bytes:
        # order keys by ascending weight (drop least important first)
        order = sorted(keys, key=lambda kk: int(weights.get(kk, 1)))
        for k in order:
            lst = brief.get("evidence", {}).get(k)
            if not isinstance(lst, list) or not lst:
                continue
            # drop in chunks to converge quickly but deterministically
            while lst and _json_bytes(brief) > max_prompt_bytes:
                drop_n = 1
                # adaptive chunking
                if len(lst) > 80:
                    drop_n = 10
                elif len(lst) > 20:
                    drop_n = 5
                else:
                    drop_n = 1
                new_len = max(0, len(lst) - drop_n)
                dropped = len(lst) - new_len
                brief["evidence"][k] = lst[:new_len]
                lst = brief["evidence"][k]
                trace["fallback_drops"].append({"key": k, "dropped": int(dropped), "remaining": int(new_len)})
                if _json_bytes(brief) <= max_prompt_bytes:
                    break

    after2 = _json_bytes(brief)
    trace["after_bytes"] = int(after2)
    trace["ok"] = bool(after2 <= max_prompt_bytes)
    return brief, trace
