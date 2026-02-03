> [!IMPORTANT] Non-authoritative
> This document is **background**. For authoritative contracts, start at:
> - `docs/contracts/README.md`

# orchestrator-installer

Installs the **taks orchestrator master** on an Ubuntu 22.04 EC2 instance.

## DNS scopes & assumptions

See: `../../docs/DNS.md`

This installer supports:

- **Static DNS** (manually managed A/AAAA records)
- **Cloud-scoped DNS** (e.g. Route53 for orchestration)

Route53 is **only required** when using automated node
provisioning and Elastic IP management.

## Required environment

Installer reads:
- `/etc/tak-orch/install.env`

Minimal required:
- `FQDN` (public hostname of orchestrator, e.g. `master.aws.tak-hv-sandbox.se`)
- `LE_EMAIL` (LetsEncrypt registration email)

Valid examples:
- `master.tak-hv-sandbox.se`
- `master.aws.tak-hv-sandbox.se`

Example:
FQDN=master.aws.tak-hv-sandbox.se
LE_EMAIL=alexander.havang@gmail.com

markdown
Copy code

## What it installs/configures

- Packages: nginx, certbot (+ nginx plugin), python venv tooling, etc
- Backend service: `taks-orch.service` (uvicorn + FastAPI)
- Nginx:
  - port 80: serves ACME HTTP-01 and redirects to HTTPS
  - port 443: terminates TLS (LetsEncrypt)
- LetsEncrypt:
  - obtains/renews cert for `$FQDN` using HTTP-01 via nginx

## Runbook

Plan:
- `orch-install plan`

Apply:
- `orch-install apply`

Verify:
- `orch-install verify`
  - checks nginx active
  - checks LetsEncrypt cert exists
  - checks HTTPS responds

## Notes / known sharp edges

- Port 80 must be reachable from the internet during cert issuance (HTTP-01).
- DNS A record for `$FQDN` must point to this instance public IP (Elastic IP recommended).
- Avoid enabling multiple port-80 vhosts simultaneously; converge to a single canonical config.
