# orchestrator-installer Contract (Authoritative)

This document is the **contract** for orchestrator-installer (master host converger).

## Scope

orchestrator-installer installs and converges the orchestrator host:
- nginx ownership of ports 80/443
- Let’s Encrypt HTTP-01 issuance/renewal
- orchestrator backend service wiring (systemd)

## Inputs

Installer reads:
- `/etc/tak-orch/install.env`

Minimum required:
- `FQDN` (public orchestrator hostname)
- `LE_EMAIL`

## Runtime contract

Backend:
- systemd service: `taks-orch.service`
- binds: `127.0.0.1:8090` (never exposed directly)

nginx:
- single canonical vhost enabled for 80/443
- port 80: ACME challenge + redirect to HTTPS
- port 443: TLS termination + reverse proxy to backend

Important:
- ACME webroot must be served from disk for HTTP-01.

## Verification contract

`orch-install verify` must validate:
- nginx is active and config tests clean
- Let’s Encrypt cert exists for FQDN
- HTTPS responds as expected
