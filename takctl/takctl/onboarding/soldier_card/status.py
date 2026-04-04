from __future__ import annotations


def cot_seen_from_device(lifecycle: dict | None) -> bool:
    if not isinstance(lifecycle, dict):
        return False
    ev = lifecycle.get("evidence") or {}
    if not isinstance(ev, dict):
        return False
    if bool(ev.get("seen_recently")) or bool(ev.get("cot_seen")):
        return True
    act = ev.get("activity") or {}
    if isinstance(act, dict) and bool(act.get("is_current")):
        return True
    return False


def mobile_flow_btn_extra_class(lifecycle: dict | None) -> str:
    return " choicebtn-ok" if cot_seen_from_device(lifecycle) else ""
