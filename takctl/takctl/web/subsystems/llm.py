from __future__ import annotations

NAME = "llm"

def register(app):
    """
    LLM subsystem:
    - Best-effort import of takctl.web.api.llm_views (may fail if optional deps missing)
    - If it imports, we include its router.
    """
    # Import inside register() so failures don't crash webapp startup.
    from takctl.web.api import llm_views

    router = llm_views.router

    # Avoid double-prefixing:
    prefix = getattr(router, "prefix", "") or ""
    if prefix in ("", "/"):
        app.include_router(router, prefix="/api/llm")
        mounted_as = "/api/llm/*"
    else:
        app.include_router(router)
        mounted_as = f"{prefix}/*"

    return {"mounted_as": mounted_as}
