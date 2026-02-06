> [!IMPORTANT] Non-authoritative  
> This document is **background**. For authoritative contracts, start at:
> - `docs/contracts/README.md`

# taks-orchestrator

This is the **orchestrator master**.  
It hosts the orchestration **API + Web UI** and is responsible for launching and managing TAK nodes (AWS first).

The orchestrator is a **control plane only**. It does not run TAK itself.

---

## DNS scopes & naming

See: `../../docs/DNS.md` (authoritative)

The orchestrator supports **multiple DNS scopes**.

### Current / static (minimum required)
- Orchestrator: `master.tak-hv-sandbox.se`
- Nodes: `<battalion>.tak-hv-sandbox.se`

### Cloud-scoped (optional orchestration target)
- Orchestrator: `master.aws.tak-hv-sandbox.se`
- Nodes: `<battalion>.aws.tak-hv-sandbox.se`

Cloud-scoped zones are intended for:
- Elastic IPs
- Route53 automation
- Fully dynamic provisioning

They are **not required** to run the orchestrator.

---

## Web wiring (current, stable)

### Components
- **Backend**: FastAPI (uvicorn)  
  - binds to `127.0.0.1:8090`
- **Web UI**: served by backend at `/`
- **CLI**: uses the same backend logic via `orchestrator_core`
- **nginx**: public entrypoint (80/443)

### Public endpoints
- `https://<orch-fqdn>/healthz`
  - served directly by nginx (static 200 `ok`)
- `https://<orch-fqdn>/openapi.json`
  - proxied by nginx → backend
- `https://<orch-fqdn>/`
  - Web UI (auth-gated)
- `https://<orch-fqdn>/login`
  - login page

---

## Authentication model (current)

- Cookie-based authentication
- Single operator password (for now)
- Runtime secrets stored in:
  - `/opt/tak-orch/state/defaults.env`

Required variables:
- `TAKS_UI_PASSWORD`
- `TAKS_UI_SECRET`

Auth flow:
1. Unauthenticated access to `/` → redirect to `/login`
2. `POST /login` sets `taks_auth` cookie
3. Cookie gates:
   - `/`
   - all UI-facing actions

This is intentionally simple and will evolve later.

---

## API (current)

All APIs are versioned under `/api/v1`.

### Status
- `GET /api/v1/status`
  - Canonical orchestrator status
  - Used by **both Web UI and CLI**


### Nodes
- `POST /api/v1/nodes/preview`
- `POST /api/v1/nodes/dry-run`
- `POST /api/v1/nodes/launch`

Request schema:
- `NodeReq` (see OpenAPI)

---

## CLI + WebUI relationship (important)

- CLI and Web UI **share the same backend wiring**
- All orchestration logic lives in:
  - `orchestrator_core`
- CLI calls:
  - `orchestrator_core.core.get_status()` (and peers)
- Web UI calls:
  - `/api/v1/*`

There is **no duplicate orchestration logic**.

---

## Runtime services

- `taks-orch.service`
  - FastAPI backend (uvicorn)
  - binds only to `127.0.0.1:8090`
- `nginx`
  - owns ports 80/443
  - TLS termination
  - reverse proxy to backend

