# takctl Contract (Authoritative)

This document is the **contract** for takctl (CLI + web backend + UI assets).

## Scope

takctl includes:
- Python CLI
- FastAPI web backend (serves API + static UI)
- Static UI assets (no bundler requirement)
- Supporting helpers for privileged operations (e.g. UserManager integration)

## Deployment model

Runtime is authoritative:
- `/opt/tak/tools/takctl`

Source is staging:
- `/opt/taks/takctl`

Convergence is performed by tak-installer (rsync/deploy step).
Manual edits in runtime are transitional only.

## Web mounting

Public mount:
- `https://<FQDN>/takctl/`

Backend:
- `takctl-web.service` binds to `127.0.0.1:8080`

Mount rule:
- UI must work under a prefix (`/takctl/`).
- `index.html` must include `<base href="/takctl/">`.
- API calls should be relative (e.g. `api/health`) so they resolve under the base.

## Privilege model

Reads:
- CoreConfig.xml and UserAuthenticationFile.xml (as referenced by CoreConfig)
- DB access is read-only by default unless explicitly documented otherwise.

Writes:
- Must be mediated via controlled helper(s) + sudoers-limited scope.
- No direct root logic inside the web backend.

## API contract (minimal)

At minimum:
- `/api/health` returns backend health
- `/openapi.json` returns OpenAPI spec

Additional endpoints are allowed, but must be stable once published.

## Failure semantics

takctl must fail loudly and clearly:
- Missing CoreConfig.xml
- CoreConfig parse errors
- Missing auth file references
- Missing UserAuthenticationFile.xml
- User not found

No silent fallbacks.

### API paths (internal vs public)

Internal (loopback, uvicorn):
- `http://127.0.0.1:8080/api/*`

Public (via nginx mount prefix):
- `https://<FQDN>/takctl/api/*`

Versioned API may be exposed under:
- `/api/v1/*`


