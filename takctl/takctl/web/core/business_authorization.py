"""Keep normal chat users out of administrative UI APIs."""
import hmac
import re
from fastapi.responses import JSONResponse

PUBLIC = frozenset(('/api/login','/api/logout','/api/whoami','/api/health','/api/meta'))
CARD = re.compile(r'^/api/onboarding/cards/[A-Za-z0-9_-]+(?:/.*)?$')


def install_business_authorization(app):
    @app.middleware('http')
    async def authorize(request, call_next):
        path=request.url.path.rstrip('/')
        if (not path.startswith('/api/') or path in PUBLIC or CARD.fullmatch(path)
            or path.startswith('/api/orchestrator/') or path.startswith('/api/martine/')):
            return await call_next(request)
        # The authenticated Business MCP's fixed loopback requests carry an
        # internal bearer. No general loopback or user-supplied role bypass.
        if request.client and request.client.host in ('127.0.0.1','::1'):
            from takctl.web.api.orchestrator import _read_local_orchestrator_secret
            expected=_read_local_orchestrator_secret()
            supplied=request.headers.get('authorization','')
            if expected and hmac.compare_digest(supplied,'Bearer '+expected):
                return await call_next(request)
        from takctl.services.business_access import request_actor
        try:
            actor=request_actor(request)
        except PermissionError:
            return JSONResponse({'detail':'Authentication required'},status_code=401)
        if not actor['admin']:
            return JSONResponse({'detail':'Administrator access required'},status_code=403)
        return await call_next(request)
