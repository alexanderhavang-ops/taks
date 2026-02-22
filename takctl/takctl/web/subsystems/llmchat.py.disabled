from __future__ import annotations

from fastapi import FastAPI

from takctl.web.api.llm_chat import router as llm_chat_router


def init(app: FastAPI) -> dict:
    """
    Optional subsystem: llmchat tool-loop endpoint.

    Exposes:
      POST /api/llm/chat
    """
    app.include_router(llm_chat_router)
    return {
        "name": "llmchat",
        "ok": True,
        "endpoints": ["/api/llm/chat"],
    }

