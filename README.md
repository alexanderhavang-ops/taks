# TAKS – TAK Server Infrastructure & Installer

TAKS is an opinionated infrastructure and installer framework for deploying,
operating, and maintaining TAK server nodes (battalion-level) in both **online**
and **offline / air-gapped** environments.

The system is split into two major components:

- **Orchestrator** – central control plane, certificate authority (via Let’s Encrypt),
  UI, and fleet state tracking
- **tak-node** – battalion TAK server node, fully owned and managed by the installer

This repository currently focuses on:
- Secure, reproducible node provisioning
- Nginx hardening and ingress ownership
- Certificate lifecycle management
- Clear operational state reporting (green / yellow / red)

---

## Core design principles

- **Installer owns the node**
  - OS configuration, nginx, systemd, TLS, and runtime layout are installer-managed
  - No manual snowflakes

- **Explicit state, not assumptions**
  - Certificate status, reachability, and install state are tracked explicitly
  - Offline actions are first-class, not hacks

- **Online-first, offline-capable**
  - Online nodes can self-renew via Let’s Encrypt HTTP-01
  - Offline nodes are supported via orchestrator-issued artifacts

- **Wildcard-first TLS**
  - Default model uses `*.tak-hv-sandbox.se`
  - Per-node certs remain possible in the future

---

## Documentation

- [`docs/certificates.md`](docs/certificates.md) – TLS & certificate lifecycle
- [`docs/orchestrator.md`](docs/orchestrator.md) – Orchestrator responsibilities & UI
- [`docs/tak-node.md`](docs/tak-node.md) – Node architecture & installer behavior
- [`tak-installer/README.md`](tak-installer/README.md) – Installer internals

---

## Current scope

✔ Nginx hardening & ownership  
✔ TLS via Let’s Encrypt  
✔ Online nodes (HTTP-01)  
✔ Wildcard certificate model  
✔ Smoke tests & health checks  

⏳ Offline nodes (artifact-based cert install)  
⏳ TAK server install (CoreConfig, Marti, federation)  

## Source → Runtime Convergence (IMPORTANT)

TAKS explicitly separates **source** and **runtime**:

- **Source (git, sanitizable)**
  - `/opt/taks`
  - Contains takctl source code, installer logic, templates, and docs
  - Never contains secrets, host-specific config, or runtime state

- **Runtime (installer-owned)**
  - `/opt/tak/tools/takctl`
  - Contains deployed takctl code, virtualenv, rendered config, logs, and state
  - May drift temporarily, but is converged by `tak-installer apply`

### takctl deployment model

takctl is deployed to runtime via an **installer-managed rsync step**:

- Source: `/opt/taks/takctl/`
- Runtime: `/opt/tak/tools/takctl/`

The installer:
- Syncs code and static assets
- Prunes stale backup files
- Explicitly preserves runtime-only paths:
  - `.venv/`
  - `secrets/`
  - `takctl.conf`
  - `takctl.audit.log`
  - `backup/`, `ignite/work/`, caches

Manual edits in runtime are transitional only.

---

## Non-goals (for now)

- User / cert lifecycle UX in ATAK
- Multi-region orchestration
- HA TAK clustering


## Example: Full Dry-Run on a Node

```bash
cd /opt/taks
export FQDN=46hvbat.tak-hv-sandbox.se
./tak-installer/tak-installer apply --dry-run

