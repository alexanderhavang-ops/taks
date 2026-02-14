# orchestrator-installer Contract (Authoritative)

This document defines the contract for orchestrator-installer
(the master host converger).

The installer owns host-level convergence of the orchestrator.

---

## Scope

The installer must:

- Install nginx
- Own ports 80 and 443
- Configure Let’s Encrypt (HTTP-01)
- Install and manage systemd service `taks-orch.service`
- Ensure required Python runtime dependencies exist
- Wire environment configuration correctly
- Converge runtime directory structure

The installer does not own orchestration logic.

---

## Required Inputs

Read from:

/etc/tak-orch/install.env


Minimum required:

- `FQDN`
- `LE_EMAIL`

---

## Required Runtime Environment

The backend requires:

- fastapi
- uvicorn[standard]
- boto3
- jinja2
- pyyaml
- python-multipart

Installer must ensure these exist even if no requirements.txt is present.

---

## Runtime Environment Files

Runtime state directory:

/opt/tak-orch/state/


Launch overrides:

/etc/taks/orchestrator.env


The installer must ensure environment variables are loaded
into the systemd unit.

---

## Required Launch Variables

The following must be satisfied before node launch is permitted:

- `TAKS_LAUNCH_ENABLED=1`
- `TAKS_AWS_SG_ID`
- `TAKS_AWS_KEY_NAME`
- `TAKS_BUNDLE_SECRET`
- `TAKS_PUBLIC_BASE_URL`

`TAKS_PUBLIC_BASE_URL` must equal:

https://<FQDN>


It must reflect the externally reachable HTTPS endpoint.

---

## Service Contract

Systemd service:

taks-orch.service


Backend:

- binds to `127.0.0.1:8090`
- never binds publicly

nginx:

- port 80:
  - ACME challenge
  - redirect to HTTPS
- port 443:
  - TLS termination
  - reverse proxy to backend

ACME webroot must be served from disk.

---

## Verification Contract

`orch-install verify` must validate:

- nginx is active
- nginx config test passes
- Let's Encrypt certificate exists
- HTTPS endpoint responds correctly
- Backend reachable via reverse proxy
- `/api/v1/status` responds over HTTPS

---

## Drift Model

Manual edits under `/opt/tak-orch` are transitional.

The installer is authoritative for:

- nginx configuration
- systemd wiring
- runtime directory structure
- service enablement

Drift must be eliminated on `apply`.

---

## Security Model

- Backend never exposed directly
- TLS termination always handled by nginx
- Secrets stored in runtime state
- No private bind address ever exposed externally

---

This contract governs host convergence only.
Orchestration behavior is defined in:

`ORCHESTRATOR-CONTRACT.md`

