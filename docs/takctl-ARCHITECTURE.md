# takctl / takctl-web architecture

## Purpose
This repo contains orchestration + installer tooling for TAK, including takctl (CLI + web UI/backend).
The goal is to make it easy to:
- inspect server state (clients, certs, CRL, users) safely
- manage users/certs (writes) via UserManager.jar while *reads* come from UserAuthenticationFile.xml

## High-level components

### 1) takctl CLI
- Python CLI for admin operations
- Reads config from: `takctl.conf`
- Uses DB read-only queries for some endpoints (clients, certs, CRL sanity)
- Uses UserAuthenticationFile.xml for user reads (list/detail)
- Uses `takctl-usermgr` helper + sudo for user/cert modifications (writes)

### 2) takctl-web backend (FastAPI)
- Runs under systemd: `takctl-web.service`
- Binds: `127.0.0.1:8080`
- Serves:
  - API endpoints under `/api/...`
  - Static UI assets at `/` (index.html + JS + CSS)
- Must produce clean actionable errors (no silent fallbacks)

### 3) Nginx reverse proxy
- Public mount under: `https://<fqdn>/takctl/`
- Proxies `/takctl/` -> `http://127.0.0.1:8080/`
- IMPORTANT: trailing slash on `proxy_pass` so paths map correctly.

## Ports
- `8080/tcp` : takctl-web backend (loopback only)
- `443/tcp`  : public HTTPS, includes `/takctl/` mount (nginx)

## Privileges & users
- takctl-web should run as a non-root user where possible (ideally `tak`), but must have:
  - read access to CoreConfig.xml + UserAuthenticationFile.xml
  - DB read access (for clients/certs/crl status if DB-backed)
- User reads:
  - MUST read auth XML referenced from CoreConfig.xml `<auth><File location="..."/></auth>`
- User writes:
  - allowed via UserManager.jar invoked through a controlled helper (sudoers-limited)

## Endpoints (backend)
- `/api/health`        : backend health
- `/api/crl/status`    : CRL existence + mtime + sample serials
- `/api/clients`       : recent clients (DB)
- `/api/certs`         : certs (DB)
- `/api/users`         : list users (auth XML)
- `/api/users/{name}`  : user detail (auth XML)
- `/openapi.json`      : OpenAPI spec

## Configuration assumptions
- `takctl.conf` contains `coreconfig_path` (example: `/opt/tak/CoreConfig.xml`)
- CoreConfig.xml contains:
  - `<auth><File location="UserAuthenticationFile.xml"/></auth>`
- Relative file paths in CoreConfig.xml are resolved relative to CoreConfig.xml directory (typically `/opt/tak/`)

## Common failure modes + expected errors
- Missing CoreConfig.xml:
  - error: "CoreConfig not found: ..."
- CoreConfig parse error:
  - error: "Failed to parse CoreConfig.xml: ..."
- Missing `<auth><File location=...>`:
  - error: "Could not find <auth>...<File location=...> in CoreConfig.xml"
- Missing UserAuthenticationFile.xml:
  - error: "User auth XML not found: ..."
- User not found:
  - HTTP 404 with clear message

## Notes on static assets
- index.html must reference assets that actually exist.
- Prefer single source of truth for react bundles: `/vendor/...` (not both `/static/vendor/...` and `/vendor/...`).

## Change log (human)
- Keep short notes of non-obvious changes here (proxy paths, service user changes, config moves).

## Development + runtime invariants

- **Runtime is authoritative:** systemd and production execution use `/opt/tak/tools/takctl`.
- **Source is staging:** changes under `/opt/taks/takctl` take effect only after `tak-installer apply` (action `takctl-runtime`) converges source → runtime.
- **Use the runtime venv:** run takctl with `/opt/tak/tools/takctl/.venv/bin/python` (system python is not supported).
