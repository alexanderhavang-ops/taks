# TAK Node Contract (Authoritative)

This document is the **contract** for a TAKS-managed TAK node (battalion node).
If anything conflicts with other docs, **this doc wins**.

## Scope

A TAK node is the battalion runtime host that runs:
- TAK Server (Marti)
- takctl (CLI + web backend)
- nginx ingress owned by tak-installer
- optional LLM proxying (if configured)

## Ownership model

**tak-installer owns the node.** Manual changes are transient.

Installer-owned (examples):
- nginx core config + snippets + vhosts
- systemd units
- TLS file placement + permissions
- runtime layout under `/opt/tak`

Not owned:
- External DNS delegation (outside node)
- Orchestrator decisions/policy

## Runtime layout

- Source repo (sanitizable): `/opt/taks`
- Runtime (authoritative): `/opt/tak`

takctl runtime:
- `/opt/tak/tools/takctl` is produced by installer convergence from `/opt/taks/takctl`

Preserved runtime-only paths (never overwritten):
- `.venv/`
- `secrets/`
- `takctl.conf`
- logs/backups/state (as defined by deploy script)

## Port model

Canonical ports on a TAK node:

- **80/tcp**: ACME HTTP-01 only (`/.well-known/acme-challenge/*`), everything else redirects to HTTPS
- **443/tcp**: takctl Web UI mount (nginx reverse proxy to loopback takctl backend)
- **8446/tcp**: client-facing “front door” (nginx reverse proxy to Marti on 8447)
- **8447/tcp**: internal Marti HTTPS (never exposed to internet)
- **8089/tcp**: CoT TLS (TAK server binds directly; no nginx)

Federation ports exist per CoreConfig.xml; out of initial scope but must be preserved.

## TLS contract

Default:
- Node does **not** self-issue certs.
- Node expects cert material to be present (typically orchestrator-provided wildcard).

Optional (explicitly enabled):
- Node may self-issue/renew via HTTP-01 if online and configured.

Offline:
- Node must boot and operate without internet.
- Updates may be applied via removable media.

## nginx contract

- nginx config is installer-rendered and deterministic.
- Sites are enabled via symlinks in `/etc/nginx/sites-enabled/`.
- takctl is mounted at: `https://<FQDN>/takctl/`
- `/` on 443 may intentionally be 404 (reserved for future routing).

## Health / verification

A node is GREEN when:
- `tak-installer apply` is clean
- systemd units are active (takctl backend)
- nginx `-t` passes and reloads cleanly
- 443 mount responds
- 8446 front door responds

### Exposure rule
Only 80/443/8446 are intended to be internet-exposed. All other ports are loopback/LAN-only and must not be opened in security groups.

