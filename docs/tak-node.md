> [!IMPORTANT] Non-authoritative
> This document is **background**. For authoritative contracts, start at:
> - `docs/contracts/README.md`

# TAK Node Architecture

Each TAK node is a fully installer-owned system.

The node is converged using:

    tak-installer apply

Manual changes are unsupported and treated as transient.

---

## Installer ownership (non-negotiable)

The installer manages:

- nginx core config
- nginx snippets and vhosts
- systemd units
- TLS certificates
- File layout under /opt/tak and /opt/taks

Manual edits are not durable and will be overwritten on the next apply.

---

## Source vs Runtime (critical distinction)

TAKS explicitly separates source from runtime.

Source (staging, git-managed):
- Path: /opt/taks
- Contains:
  - tak-installer
  - takctl source code
  - infra templates
  - documentation
- Sanitizable, no secrets

Runtime (authoritative, systemd-owned):
- Path: /opt/tak/tools/takctl
- Contains:
  - deployed takctl code
  - Python virtualenv (.venv)
  - rendered config (takctl.conf)
  - runtime logs and state

Invariant:
If takctl-web.service is running, then:
- /opt/tak/tools/takctl was produced by tak-installer
- code, service units, and nginx wiring are aligned

---

## takctl runtime deployment model

- takctl is not git-cloned on the node
- takctl is not pip-installed
- takctl runtime is rsync-deployed from source

    /opt/taks/takctl  →  /opt/tak/tools/takctl

Preserved runtime state:
- .venv/
- secrets/
- takctl.conf
- takctl.audit.log
- backup/
- ignite/work/

This allows safe redeploys on live systems.

---

## TLS behavior

Default:
- Node expects certificate material to exist
- Does not self-issue
- Uses wildcard cert from orchestrator

Optional (explicit):
- HTTP-01 self-issuance
- Online nodes only

Offline / air-gapped nodes are first-class.

---

## Health & verification

Each node exposes:
- Local health endpoint (loopback)
- Nginx-fronted health endpoint
- Installer smoke tests

Nodes can report:
- Installed cert serial
- Installer version
- Last successful apply

---

## Nginx site naming convention

For a node FQDN:

443 (takctl):
- sites-available/tak-<FQDN>-443.conf
- sites-enabled/tak-<FQDN>-443.conf

8446 (frontdoor):
- sites-available/tak-<FQDN>-enroll-8446.conf
- sites-enabled/tak-<FQDN>-enroll-8446.conf

80 (ACME only):
- sites-available/80-acme-redirect
- sites-enabled/80-acme-redirect

Sites are enabled via symlinks:
- /etc/nginx/sites-enabled → ../sites-available

---

## Default tak-node plan order

1. takctl-runtime
2. systemd.takctl-web
3. nginx.core
4. nginx.snippets.core
5. nginx.acme
6. nginx.443.takctl
7. nginx.8446.frontdoor

Do not reorder casually.

---

# TAK Node Bootstrap Checklist (Operator Guide)

## 1. Base OS assumptions
- Ubuntu LTS
- nginx installed
- systemd available
- /opt/taks present
- /opt/tak installer-owned

---

## 2. Required environment variables

Export one of:

    export FQDN=46hvbat.tak-hv-sandbox.se
    # or
    export TAKS_FQDN=46hvbat.tak-hv-sandbox.se

tak-installer is intentionally non-interactive.

---

## 3. Mandatory dry-run

    cd /opt/taks
    ./tak-installer/tak-installer apply --dry-run

Dry-run:
- Executes full plan
- Validates env vars
- Uses DRY_RUN=1
- Makes no changes

---

## 4. Fix reported errors

Common failures:
- Missing FQDN
- Missing certs
- nginx config errors

Never work around installer errors.

---

## 5. Apply for real

    ./tak-installer/tak-installer apply

Apply auto-elevates via sudo if needed.

---

## 6. Verify takctl

    systemctl status takctl-web.service
    /opt/tak/tools/takctl/.venv/bin/python -m takctl.main health

---

## 7. Verify nginx

    nginx -t
    systemctl reload nginx

Check:
- https://<FQDN>/takctl/
- https://<FQDN>:8446/Marti/

---

## 8. Certificates

- Correct wildcard cert
- Correct permissions
- No direct exposure of 8447

---

## 9. Smoke tests (optional)

    /opt/taks/tools/taks-smoketest.sh

---

## 10. Node is GREEN when

- tak-installer apply exits cleanly
- takctl-web.service is active
- nginx reloads cleanly
- 443 and 8446 respond
- No manual edits were required

## takctl Web UI mount

takctl-web is served behind nginx on the 443 vhost and is **mounted at**:

- `https://<FQDN>/takctl/`

Behavior:
- `/` on 443 is **intentionally 404** (reserved for future routing; WebTak lives on 8446).
- `/takctl/` proxies to the local takctl-web backend at `http://127.0.0.1:8080/`.

### Static UI serving model

The backend serves the UI as static files (no bundler/build step):

- FastAPI mounts `takctl/web/` via `StaticFiles(..., html=True)`
- nginx reverse-proxies `/takctl/` to the backend

### Frontend pathing rules

Because the UI is mounted under a path prefix:

- `index.html` must include: `<base href="/takctl/">`
- Asset URLs should be relative (e.g. `./app.js`, `./styles.css`)
- API calls should be relative (e.g. `api/health`), or `/api/...` is rewritten to the current mount.

This prevents accidental calls to `/api/...` at the vhost root (which is 404 by design).

