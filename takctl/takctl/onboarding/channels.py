from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def uniq_channels(items: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    if not isinstance(items, (list, tuple, set)):
        return out
    for item in items:
        name = _s(item)
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _policy_id_from_ctx(ctx: dict[str, Any] | None) -> str:
    pid = _s((ctx or {}).get("policy_id"))
    if pid:
        return pid
    try:
        from takctl.onboarding.policy_registry import default_policy_id

        return _s(default_policy_id())
    except Exception:
        return ""


def _ctx_with_default_policy(ctx: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(ctx or {})
    if not _s(out.get("policy_id")):
        pid = _policy_id_from_ctx(out)
        if pid:
            out["policy_id"] = pid
    return out


def _load_policy_cfg(policy_id: str) -> dict[str, Any] | None:
    pid = _s(policy_id)
    if not pid:
        return None

    # Prefer the runtime Policy loader if it exposes a raw dict.
    try:
        from takctl.onboarding.policy import Policy

        pol = Policy(policy_id=pid)
        for attr in ("cfg", "config", "policy_cfg", "policy", "data", "raw"):
            val = getattr(pol, attr, None)
            if isinstance(val, dict):
                return val
        for meth in ("to_dict", "as_dict", "dict"):
            fn = getattr(pol, meth, None)
            if callable(fn):
                val = fn()
                if isinstance(val, dict):
                    return val
    except Exception:
        pass

    # Fallback: built-in policy JSON next to this module.
    p = Path(__file__).resolve().parent / "policies_builtin" / pid / "policy.json"
    try:
        if p.exists():
            val = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(val, dict):
                return val
    except Exception:
        pass

    return None


def _walk_dicts(v: Any):
    if isinstance(v, dict):
        yield v
        for child in v.values():
            yield from _walk_dicts(child)
    elif isinstance(v, list):
        for child in v:
            yield from _walk_dicts(child)


def _direct_battalion_fal(policy_cfg: dict[str, Any] | None, battalion: Any) -> str:
    """
    Robust fallback for policy schemas that expose e.g.
      "battalion_to_fal": {"46": "VQ", "VQ": "46"}
    but are not shaped exactly as fal.py expects.
    """
    b = _s(battalion).upper()
    if not b or not isinstance(policy_cfg, dict):
        return ""

    for d in _walk_dicts(policy_cfg):
        raw = d.get("battalion_to_fal")
        if isinstance(raw, dict):
            val = _s(raw.get(b) or raw.get(b.lower()) or raw.get(b.upper())).upper()
            if len(val) >= 2 and not val.isdigit():
                return val[:2]

        raw = d.get("fal_map")
        if isinstance(raw, dict):
            val = _s(raw.get(b) or raw.get(b.lower()) or raw.get(b.upper())).upper()
            if len(val) >= 2 and not val.isdigit():
                return val[:2]

    return ""


def augment_ctx_for_policy(ctx: dict[str, Any] | None) -> dict[str, Any]:
    """
    Voice topology needs battalion_fal. The create-user UI often has only
    battalion=46, so resolve policy FAL context before calling topology.
    """
    out = _ctx_with_default_policy(ctx)
    policy_cfg = _load_policy_cfg(_policy_id_from_ctx(out))

    if not isinstance(policy_cfg, dict):
        return out

    direct_bn_fal = _direct_battalion_fal(policy_cfg, out.get("battalion"))
    if direct_bn_fal and not _s(out.get("battalion_fal")):
        out["battalion_fal"] = direct_bn_fal

    try:
        from takctl.onboarding.fal import derive_fal_ctx

        derived = derive_fal_ctx(policy_cfg, out)
    except Exception:
        return out

    if not isinstance(derived, dict):
        return out

    for key in (
        "battalion_no",
        "battalion_fal",
        "battalion_second",
        "company_fal",
        "platoon_fal",
        "group_fal",
        "group_scope_fal",
    ):
        val = derived.get(key)
        if _s(val) and not _s(out.get(key)):
            out[key] = val

    return out


def selection_channel_names(selection: dict[str, Any] | None) -> list[str] | None:
    """
    Return:
      - None when no explicit channel selection exists
      - list[str] when explicitly selected

    Empty explicit lists are preserved here, but effective_selected_channels()
    coerces them back to derived defaults. The onboarding UI should not create
    "no channel" voice packages by accident.
    """
    if not isinstance(selection, dict):
        return None
    if "channels" not in selection:
        return None

    raw = selection.get("channels")
    if isinstance(raw, dict):
        for key in ("selected", "rooms", "names", "channels"):
            if key in raw:
                return uniq_channels(raw.get(key) or [])
        return None

    if isinstance(raw, list):
        return uniq_channels(raw)

    return None


def derive_channel_sets(ctx: dict[str, Any] | None) -> dict[str, Any]:
    ctx2 = augment_ctx_for_policy(ctx)
    policy_cfg = _load_policy_cfg(_policy_id_from_ctx(ctx2))

    try:
        from takctl.onboarding.voice_topology import derive_voice_topology

        topo = derive_voice_topology(policy_cfg, ctx2)
    except Exception as e:
        fallback = _s(ctx2.get("battalion_fal") or ctx2.get("unit") or "VQ") or "VQ"
        return {
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "topology": {},
            "available": [fallback],
            "default": [fallback],
        }

    available = uniq_channels(topo.get("channels") or [])
    default = uniq_channels(topo.get("seed_channels") or [])

    if not default:
        fallback = _s(ctx2.get("battalion_fal") or ctx2.get("unit") or "VQ") or "VQ"
        default = [fallback]

    if not available:
        available = list(default)

    return {
        "ok": True,
        "error": None,
        "topology": topo,
        "available": available,
        "default": default,
    }


def effective_selected_channels(
    ctx: dict[str, Any] | None,
    *,
    selection: dict[str, Any] | None = None,
    selected: list[str] | None = None,
) -> list[str]:
    defaults = uniq_channels(derive_channel_sets(ctx).get("default") or [])

    if selected is not None:
        explicit = uniq_channels(selected)
        return explicit if explicit else defaults

    from_selection = selection_channel_names(selection)
    if from_selection is not None:
        explicit = uniq_channels(from_selection)
        return explicit if explicit else defaults

    return defaults


def build_selection_channels(
    ctx: dict[str, Any] | None,
    *,
    selection: dict[str, Any] | None = None,
    selected: list[str] | None = None,
) -> dict[str, Any]:
    sets = derive_channel_sets(ctx)
    effective = effective_selected_channels(ctx, selection=selection, selected=selected)

    # Keep explicitly selected legacy/custom channels visible even if they are not
    # in the currently derived topology.
    available = uniq_channels(list(sets.get("available") or []) + effective)
    default = uniq_channels(sets.get("default") or [])

    return {
        "selected": effective,
        "default": default,
        "available": available,
        "derive_ok": bool(sets.get("ok")),
        "derive_error": sets.get("error"),
    }
