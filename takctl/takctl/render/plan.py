from __future__ import annotations

from typing import Any, Iterable

RENDERPLAN_VERSION = "taks.renderplan.v1"


class RenderPlanError(ValueError):
    pass


def _is_str(x: Any) -> bool:
    return isinstance(x, str)


def _is_dict(x: Any) -> bool:
    return isinstance(x, dict)


def _is_list(x: Any) -> bool:
    return isinstance(x, list)


def _req(obj: dict[str, Any], key: str, pred, msg: str) -> None:
    if key not in obj:
        raise RenderPlanError(f"missing key: {key}")
    if not pred(obj.get(key)):
        raise RenderPlanError(f"invalid {key}: {msg}")


def _opt(obj: dict[str, Any], key: str, pred, msg: str) -> None:
    if key in obj and obj.get(key) is not None and not pred(obj.get(key)):
        raise RenderPlanError(f"invalid {key}: {msg}")


def validate_renderplan(plan: Any) -> dict[str, Any]:
    if not _is_dict(plan):
        raise RenderPlanError("renderplan must be a JSON object")

    _req(plan, "schema_version", _is_str, "must be a string")
    if plan["schema_version"] != RENDERPLAN_VERSION:
        raise RenderPlanError(f"schema_version must be {RENDERPLAN_VERSION!r}")

    _req(plan, "view", _is_str, "must be a string")
    _opt(plan, "meta", _is_dict, "must be an object")
    _opt(plan, "datasets", _is_dict, "must be an object")
    _req(plan, "blocks", _is_list, "must be an array")

    for i, b in enumerate(plan["blocks"]):
        if not _is_dict(b):
            raise RenderPlanError(f"block[{i}] must be an object")
        _req(b, "type", _is_str, "must be a string")

        t = b["type"]
        if t == "header":
            _req(b, "title", _is_str, "must be a string")
            _opt(b, "subtitle", _is_str, "must be a string")
        elif t == "markdown":
            _req(b, "body", _is_str, "must be a string")
            _opt(b, "title", _is_str, "must be a string")
        elif t == "json":
            _req(b, "body", lambda _: True, "must exist")
            _opt(b, "title", _is_str, "must be a string")
        elif t == "card":
            _req(b, "title", _is_str, "must be a string")
            _opt(b, "subtitle", _is_str, "must be a string")
            _opt(b, "ingress", _is_str, "must be a string")
            _opt(b, "payload", _is_dict, "must be an object")
            payload = b.get("payload")
            if payload is not None:
                _req(payload, "type", _is_str, "must be a string")
        else:
            # Forward-compat: unknown blocks allowed (must still be object+type)
            pass

    return plan


def iter_block_types(plan: dict[str, Any]) -> Iterable[str]:
    for b in plan.get("blocks") or []:
        if isinstance(b, dict) and isinstance(b.get("type"), str):
            yield b["type"]
