from __future__ import annotations

import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from takctl.services.marti_auth import check_userauthfile
from takctl.web.session import COOKIE_NAME, SESSION_TTL, get_session, sign_session


def mount_auth_routes(app: FastAPI) -> None:
    @app.get("/api/whoami")
    async def whoami(req: Request):
        sess = get_session(req)
        if not sess:
            return JSONResponse({"authenticated": False})
        return JSONResponse({"authenticated": True, "user": {"username": sess.get("u", "")}})

    @app.get("/api/logout")
    async def logout():
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE_NAME, path="/")
        return resp

    @app.get("/api/login")
    async def login_get():
        raise HTTPException(status_code=405, detail="Use POST /api/login")

    @app.post("/api/login")
    async def login(req: Request):
        body = await req.json()
        username = str(body.get("username", "")).strip()
        password = str(body.get("password", ""))

        if not username or not password:
            raise HTTPException(status_code=400, detail="username and password required")

        res = check_userauthfile(username, password)
        if not res.ok:
            raise HTTPException(status_code=401, detail=f"Invalid credentials ({(res.error or '')[:160]})")

        sess = {"u": username, "exp": int(time.time() + SESSION_TTL)}
        token = sign_session(sess)

        resp = JSONResponse({"ok": True, "user": {"username": username}})
        resp.set_cookie(
            COOKIE_NAME,
            token,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
            max_age=SESSION_TTL,
        )
        return resp
