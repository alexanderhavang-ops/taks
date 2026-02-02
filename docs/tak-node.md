# TAK Node Architecture

Each TAK node is a fully installer-owned system.

---

## Installer ownership

The installer manages:

- nginx core config
- nginx snippets and vhosts
- systemd units
- TLS certificates
- File layout under `/opt/taks`

Manual edits are unsupported.

### takctl runtime

The installer owns the takctl runtime deployment:

- Code is synced from source on each apply
- Runtime-only artifacts are preserved
- takctl-web is restarted only after code convergence

This avoids partial upgrades and drift between code and service state.

---

## TLS behavior

By default:
- Node expects certificate material to be present
- Does not attempt to self-issue
- Uses wildcard cert provided by orchestrator

Optional:
- HTTP-01 self-issuance (online only)
- Must be explicitly enabled

---

## Health & verification

Each node exposes:
- Local health endpoint (loopback)
- Nginx fronted health endpoint
- Installer smoke tests

Nodes can report:
- Installed cert serial
- Installer version
- Last successful apply

---

## Offline readiness

Nodes are designed to:
- Boot without internet
- Operate indefinitely with valid cert
- Be updated via removable media

This is intentional.

### Invariant

If `takctl-web.service` is running, then:
- `/opt/tak/tools/takctl` was produced by tak-installer
- Code, service, and nginx wiring are aligned

### Nginx site naming convention

tak-installer renders and enables nginx sites deterministically.

For a node FQDN, the installer uses:

- 443 (takctl):
  - sites-available: `tak-<FQDN>-443.conf`
  - sites-enabled:   symlink to sites-available

- 8446 (frontdoor/enrollment):
  - sites-available: `tak-<FQDN>-enroll-8446.conf`
  - sites-enabled:   symlink to sites-available

- 80 (ACME only):
  - sites-available: `80-acme-redirect`
  - sites-enabled:   symlink to sites-available

This supports multiple nodes/templates cleanly and avoids manual naming drift.


### Nginx enablement model

tak-installer enables nginx sites by creating symlinks:

- `/etc/nginx/sites-enabled/<name>` → `/etc/nginx/sites-available/<name>`

This is the canonical Debian/Ubuntu nginx model and is required for deterministic ownership.

## Default tak-node plan order

Typical plan execution order:

1. `takctl-runtime`        (sync source → runtime)
2. `systemd.takctl-web`    (unit convergence)
3. `nginx.core`            (nginx.conf + mime.types + logformats)
4. `nginx.snippets.core`   (shared hardening snippets)
5. `nginx.acme`            (port 80 ACME-only site)
6. `nginx.443.takctl`      (takctl UI mount)
7. `nginx.8446.frontdoor`  (TAK enrollment + WebTAK + Marti proxy)

This order is deliberate and should not be changed casually.

