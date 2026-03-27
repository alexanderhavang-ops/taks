from __future__ import annotations


def safe(v: object) -> str:
    return "" if v is None else str(v)


def getv(thing, key: str, default=None):
    if thing is None:
        return default
    if isinstance(thing, dict):
        return thing.get(key, default)
    return getattr(thing, key, default)


def ctx_from(ident, sel: dict) -> dict:
    out: dict = {}

    ident_ctx = getv(ident, "ctx", None) or {}
    ident_identity = getv(ident, "identity", None) or {}

    if isinstance(ident_ctx, dict):
        out.update(ident_ctx)
    if isinstance(ident_identity, dict):
        for k, v in ident_identity.items():
            if k not in out and v is not None:
                out[k] = v

    sel_ctx = (sel or {}).get("ctx") or {}
    if isinstance(sel_ctx, dict):
        for k, v in sel_ctx.items():
            if k not in out and v is not None:
                out[k] = v

    return out


def norm(s: object) -> str:
    return str(s).strip() if s is not None else ""


def pill(text: str, cls: str = "") -> str:
    from html import escape as h
    c = ("pill " + cls).strip()
    return f'<span class="{c}">{h(text)}</span>'


def row(label: str, html_value: str) -> str:
    from html import escape as h
    if not html_value:
        return ""
    return f'<div class="row"><b>{h(label)}</b>: {html_value}</div>'


def code(v: object) -> str:
    from html import escape as h
    if v is None:
        return ""
    s = norm(v)
    if not s:
        return ""
    return f"<code>{h(s)}</code>"


def boolpill(v: bool, *, yes: str = "yes", no: str = "no") -> str:
    return pill(yes if v else no, "meta")


def fmt_dt(v: object) -> str:
    s = norm(v)
    if not s:
        return ""
    return code(s)
