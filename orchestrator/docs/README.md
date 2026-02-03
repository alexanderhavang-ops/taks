> [!IMPORTANT] Non-authoritative
> This document is **background**. For authoritative contracts, start at:
> - `docs/contracts/README.md`

# taks-orchestrator

This is the **orchestrator master**: it hosts the orchestration API/UI and is responsible for launching TAK nodes (AWS for now).

## Frozen DNS & naming

See: `../../docs/DNS.md`

We use a cloud-scoped delegated zone:

- Orchestrator: `master.aws.tak-hv-sandbox.se`
- Nodes: `<battalion>.aws.tak-hv-sandbox.se` (e.g. `48hvbat.aws.tak-hv-sandbox.se`)

The orchestrator should use an Elastic IP.

## Web wiring (current)

### Components
- **Backend**: FastAPI (uvicorn) on `127.0.0.1:8090`
- **Frontend**: currently served by the backend root (`/`) (HTML)
- **Nginx**: public entrypoint on 80/443

### Public endpoints
- `https://<orch-fqdn>/healthz`
  - served directly by nginx (static 200 "ok")
- `https://<orch-fqdn>/openapi.json`
  - proxied by nginx → backend (FastAPI)
- `https://<orch-fqdn>/` (UI)
  - proxied by nginx → backend (FastAPI)

### Nginx sites (current state)
- `/etc/nginx/sites-enabled/orch-master.conf`
  - canonical 80/443 for orchestrator FQDN
  - 80 serves ACME challenge and redirects everything else → HTTPS
  - 443 serves `/healthz` directly; `/` returns a placeholder text (may be replaced by proxy rules as we converge)
- `/etc/nginx/sites-enabled/taks-orchestrator-http.conf`
  - port 80 reverse-proxy to backend (used for local/dev and some transitions)
  - NOTE: this can conflict with canonical redirect behavior; long term we should converge to **one canonical nginx site**.

## API (current)

The backend exposes:
- `POST /api/nodes/preview`
- `POST /api/nodes/dry-run`
- `POST /api/nodes/launch`

Schema:
- `NodeReq` is the request body model (see OpenAPI).

## Runtime services
- `taks-orch.service` runs the backend (uvicorn)
- `nginx` is the public reverse proxy / TLS termination
