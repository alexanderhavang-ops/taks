from __future__ import annotations

from fastapi import FastAPI


def init(app: FastAPI) -> dict:
    """
    Optional subsystem: LLM views + planner endpoints.

    Pure systemd model:
      - systemd timer runs generators that write state files
      - web only reads cached files + debug introspection

    Routers:
      - takctl.web.api.llm_views   (existing cached outputs)
      - takctl.web.api.llm_debug   (new GET-only introspection)
    """
    from takctl.web.api.llm_views import router as llm_router
    from takctl.web.api.llm_debug import router as llm_debug_router

    app.include_router(llm_router)
    app.include_router(llm_debug_router)

    return {
        "name": "llm",
        "ok": True,
        "endpoints": [
            # cached outputs (existing)
            "/api/llm/views/tactical/latest",
            "/api/llm/views/tactical/snapshot",
            "/api/llm/views/tactical/last_run",
            # debug introspection (new)
            "/api/llm/views/tactical/debug/state",
            "/api/llm/views/tactical/debug/events",
            "/api/llm/views/tactical/debug/artifacts",
            "/api/llm/views/tactical/debug/artifact/{name}",
        ],
    }
