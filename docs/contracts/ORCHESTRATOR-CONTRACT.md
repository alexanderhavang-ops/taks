# Orchestrator Contract (Authoritative)

This document defines the **authoritative contract** for the TAKS Orchestrator (control plane).

The orchestrator is a control-plane system responsible for provisioning,
artifact distribution, lifecycle tracking, and orchestration of TAK nodes.

It does not run TAK itself.

---

## Scope

The orchestrator owns:

- Node state tracking
- Node launch automation (AWS first, implemented)
- Cloud-init rendering for nodes
- Signed artifact distribution (installation bundles)
- Certificate lifecycle management
- Offline artifact workflows
- Operator-facing API + Web UI
- Shared backend logic for CLI and Web

The orchestrator is the **single source of truth** for node lifecycle state.

---

## Architecture Model

### Control Plane Only

The orchestrator:

- Does not run TAK
- Does not proxy TAK traffic
- Does not serve enrollment endpoints

Nodes are separate runtime systems.

---

## Runtime Topology

Backend:
- FastAPI (uvicorn)
- Binds to `127.0.0.1:8090` only

Public ingress:
- nginx
- Ports 80/443
- TLS termination (Let’s Encrypt)
- Reverse proxy to backend

The backend is never exposed directly.

---

## Public API Model

All APIs are versioned under:

/api/v1


Canonical endpoints include:

- `GET /api/v1/status`
- `POST /api/v1/nodes/preview`
- `POST /api/v1/nodes/dry-run`
- `POST /api/v1/nodes/launch`

CLI and Web UI both consume the same backend logic.

There is no duplicated orchestration logic.

---

## Node Launch Model (AWS-first)

Node launch is implemented.

The orchestrator:

1. Receives `NodeReq`
2. Renders cloud-init template
3. Mints signed bundle URL
4. Launches EC2 instance
5. Embeds bootstrap configuration into cloud-init

Cloud-init writes:

- `/etc/taks/node.env`
- `/etc/taks/orchestrator.env`
- `/etc/taks/bundle.env`
- `/usr/local/sbin/taks-bootstrap.sh`

The bootstrap script is responsible for:
- Fetching installation bundle
- Verifying integrity
- Executing installation logic
- Logging explicitly
- Failing hard on error

---

## Bundle Distribution Model

Nodes receive installation bundles via **short-lived signed URLs**.

Properties:

- URLs are minted by the orchestrator API
- Tokens are time-limited
- Tokens are single-purpose
- URLs must be externally reachable by nodes
- URLs must use HTTPS

### Public Base URL

Signed URLs must be derived from:

TAKS_PUBLIC_BASE_URL


This value represents the externally reachable HTTPS FQDN
(e.g. `https://master.tak-hv-sandbox.se`).

The orchestrator must never mint URLs using:
- `127.0.0.1`
- private bind addresses
- internal-only hostnames

If `TAKS_PUBLIC_BASE_URL` is not defined,
node launch must fail clearly.

---

## Cloud-init Rendering Contract

The cloud-init template must:

- Be valid YAML
- Contain no merge conflict markers
- Fail-fast if rendering errors occur
- Embed:
  - ORCH_API_URL
  - BUNDLE_URL
  - node-specific environment values

Rendering failures must surface before EC2 launch.

---

## Certificate Lifecycle Model

Cert deployment states are explicit and never inferred:

- ISSUED
- AVAILABLE_FOR_DOWNLOAD
- DOWNLOADED
- INSTALLED_UNVERIFIED
- INSTALLED_VERIFIED
- SUPERSEDED
- REVOKED

Online nodes may support automatic verification via
reported serial/fingerprint.

Offline nodes use explicit operator workflows.

---

## Security Model

- Private keys are never regenerated silently
- Artifact distribution uses signed short-lived URLs
- Secrets are runtime-managed
- Backend binds only to localhost
- nginx owns TLS termination

---

## Failure Model

The orchestrator must fail clearly when:

- Required launch variables are missing
- Cloud-init rendering fails
- Public base URL is undefined
- Signed URL generation fails

Silent partial launches are not allowed.

---

## Source of Truth

Authoritative DNS rules:
- `docs/DNS.md`

Authoritative installer behavior:
- `ORCHESTRATOR-INSTALLER-CONTRACT.md`

This document defines control-plane behavior only.


