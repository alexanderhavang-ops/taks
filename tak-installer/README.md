## Certificate handling

The installer does not decide *which* certificate to use.

It:
- Installs certificates provided by orchestrator
- Verifies permissions and layout
- Reloads nginx safely
- Exposes verification data when possible

All policy decisions live above the installer layer.

## takctl runtime deployment

The installer includes a dedicated action:

- **Action ID:** `takctl-runtime`
- **Purpose:** Converge takctl source → runtime

### Behavior
- Executes `/opt/taks/tak-installer/scripts/deploy-takctl-runtime`
- Uses rsync with explicit excludes
- Supports `--dry-run` and real apply

### Order in plan
This action must run **before**:
- `systemd-takctl-web`

This guarantees that:
- Code is deployed
- Then systemd restarts the web backend against the updated code

## Action Interface Contract

All tak-installer actions must follow a strict discovery and execution contract.

### Discovery
- Actions are discovered from `tak_installer/actions/*.py`
- Each module must export a global named `ACTION`
- `ACTION` must define a unique `ID` string

### Execution Interface
Each action must implement:

```python
def inspect(self, ctx) -> int:
    """Dry-run execution"""

def apply(self, ctx) -> int:
    """Real execution"""


---

## 2. Plan Files Are **Action IDs**, Not Filenames

### What we learned
Files in `plans/tak-node.d/*.action`:
- Are **not code**
- Are **not module names**
- They contain **exactly one line**: the action `ID`

The filename only controls **ordering**.

### Where to document
📄 `tak-installer/README.md`

### Suggested text

```markdown
## Plan Files (`*.action`)

Plan files define *execution order*, not behavior.

- Filename controls ordering (lexicographic)
- File contents must be the action ID
- Empty lines and comments (`#`) are ignored

Example:

```text
05-takctl-runtime.action
------------------------
takctl-runtime


---

## 3. Environment Variables Are the **Primary Installer Input API**

### What we learned
Critical actions **require env vars**, and will hard-fail without them:

| Variable      | Used by               | Required |
|---------------|----------------------|----------|
| `FQDN`        | nginx.acme            | ✅ yes |
| `TAKS_FQDN`   | nginx.acme (alt)      | optional |
| `SRC_REPO`    | takctl-runtime        | optional |
| `DST_RUNTIME` | takctl-runtime        | optional |
| `DRY_RUN`     | takctl-runtime        | internal |

No defaults. No prompts. Missing vars = crash.

## Required Environment Variables

The installer is intentionally non-interactive.
All required inputs must be provided via environment variables.

### Required
- `FQDN`  
  Fully-qualified domain name for this TAK node  
  Example:
  ```bash
  export FQDN=46hvbat.tak-hv-sandbox.se


---

## 4. takctl Runtime Is **Deployed**, Not Installed

### What we learned
`/opt/tak/tools/takctl`:
- Is **not** git-cloned
- Is **not** pip-installed
- Is **rsync-deployed** from `/opt/taks/takctl`
- Preserves runtime state:
  - `.venv`
  - `secrets/`
  - `takctl.conf`
  - logs, backups, ignite state

This is a **code sync**, not an install step.

### Where to document
📄 `docs/tak-node.md`  
📄 `docs/orchestrator.md`

### Suggested text

```markdown
## takctl Runtime Deployment Model

The takctl runtime under `/opt/tak/tools/takctl` is deployed via rsync
from the orchestration repository (`/opt/taks/takctl`).

### Preserved Runtime State
The following are never overwritten:
- `.venv/`
- `secrets/`
- `takctl.conf`
- `takctl.audit.log`
- `backup/`
- `ignite/work/`

This allows safe redeploys during live operation.

## Dry-Run Semantics

`tak-installer apply --dry-run` executes the full action chain using
each action’s `inspect(ctx)` method.

Dry-run:
- Validates environment variables
- Executes scripts with `DRY_RUN=1`
- Fails on missing inputs or paths

Dry-run is a safety check, not a simulation.

## Idempotence model (hash-based)

Most actions compare source vs destination using SHA256 checksums:

- `src sha256`: rendered template or source file
- `dst sha256`: current filesystem state

If hashes match → `status: up-to-date` and no changes occur.

This makes applies deterministic and safe to repeat.


## Required environment variables

tak-installer is intentionally non-interactive. Actions may hard-fail if required
inputs are missing.

### FQDN
Many nginx actions require the node FQDN for template rendering.

Provide one of:

- `FQDN` (preferred)
- `TAKS_FQDN` (fallback)

Example:

```bash
export FQDN=46hvbat.tak-hv-sandbox.se
./tak-installer/tak-installer apply --dry-run


## takctl Web UI integration

The takctl UI is served behind the 443 nginx vhost and is mounted at:

- `https://$FQDN/takctl/`

The vhost is installer-owned and proxies:

- `/takctl/` → `http://127.0.0.1:8080/` (takctl-web FastAPI backend)

### Why `/` is 404 on 443

The 443 vhost explicitly denies everything except `/takctl/`:

- `/` returns 404 by design
- WebTAK / Marti are exposed on the 8446 frontdoor vhost (not 443)

### Frontend mount requirements

Because the UI is mounted at `/takctl/`, the static frontend must:

- Include `<base href="/takctl/">` in `index.html`
- Use relative asset paths (e.g. `./app.js`, `./styles.css`)
- Use relative API paths (e.g. `api/health`) or rewrite `/api/...` → `<mount>/api/...`

This prevents requests from escaping the mount and hitting `/api/...` at the vhost root.
## takctl webUI behind nginx (2026-02-02)

### Where it lives

- Public URL: **https://<FQDN>/takctl/**
- Backend: `takctl-web.service` (uvicorn) on `127.0.0.1:8080`

Nginx 443 site intentionally returns **404 for `/`** and only proxies the `/takctl/` subtree:

- `/takctl/` → proxy_pass → `http://127.0.0.1:8080/`
- everything else → `return 404;`

This is deliberate so the node can later host other frontends on `/` (e.g. WebTAK) without ambiguity.

### UI mounting rules

Because the UI is mounted under a prefix:

- **HTML must include**: `<base href="/takctl/">`
- JS should call APIs using **relative paths** (e.g. `"api/health"`) so they resolve under the base.
- If any component uses absolute paths (e.g. `"/api/..."`), it must be rewritten to the current mount.

### Troubleshooting symptoms

- `404 Not Found (nginx)` at `https://<FQDN>/` is expected.
- Black screen at `/takctl/` usually means a JS runtime error. The first thing to check is the browser console and that `utils/format.js` defines the expected helpers (e.g. `h = React.createElement` if used).

