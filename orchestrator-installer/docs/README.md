# orchestrator-installer

Installs the **taks orchestrator master** on an Ubuntu 22.04 EC2 instance.

## Frozen DNS & naming

See: `../../docs/DNS.md`

This installer assumes AWS + Route53 for the delegated zone:
- `aws.tak-hv-sandbox.se`

## Required environment

Installer reads:
- `/etc/tak-orch/install.env`

Minimal required:
- `FQDN` (public hostname of orchestrator, e.g. `master.aws.tak-hv-sandbox.se`)
- `LE_EMAIL` (LetsEncrypt registration email)

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
