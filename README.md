> [!IMPORTANT] Non-authoritative
> This document is **background**. For authoritative contracts, start at:
> - `docs/contracts/README.md`

# taks

Monorepo for:
- `orchestrator/` (master/orchestrator backend + UI)
- `orchestrator-installer/` (installs orchestrator host: nginx + LE + backend service)
- `tak-installer/` (installs TAK node runtime pieces: nginx sites/snippets + takctl runtime, etc.)

## Contracts (authoritative)

Start here (these docs win on conflicts):

- `docs/contracts/README.md`

Also authoritative:
- `docs/DNS.md`

## DNS & orchestration scopes (important)

This repo intentionally supports **multiple DNS scopes**:

- **Current / legacy (static):**
  - `master.tak-hv-sandbox.se`
  - `<battalion>.tak-hv-sandbox.se`

- **Cloud-scoped (orchestration-ready):**
  - `*.aws.tak-hv-sandbox.se` (Route53 + Elastic IP)
  - future: `*.gcp.tak-hv-sandbox.se`, etc

The orchestrator and installers must support **both models concurrently**.
No automatic migration is assumed.

## Orchestrator web wiring (don’t guess)

Single source of truth:
- backend: `taks-orch.service` listens on `127.0.0.1:8090`
- public ingress: nginx owns ports 80/443 via `orch-master.conf`

Canonical nginx vhost:
- `/etc/nginx/sites-available/orch-master.conf`
- enabled via `/etc/nginx/sites-enabled/orch-master.conf`

Rules:
- Port 80: ACME HTTP-01 from disk + redirect to HTTPS
- Port 443: TLS termination + reverse proxy to `127.0.0.1:8090`

Docs:
- `orchestrator/docs/README.md`
- `orchestrator-installer/docs/README.md`

## Why local curl sometimes 404 (important)

The ACME vhost matches `server_name <FQDN>`.
So `curl http://127.0.0.1/...` uses `Host: 127.0.0.1` and may hit the wrong server block.

Use:
- `curl -H "Host: <FQDN>" http://127.0.0.1/.well-known/acme-challenge/<token>`
