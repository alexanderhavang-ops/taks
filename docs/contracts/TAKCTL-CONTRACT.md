# takctl Contract (Authoritative)

This document is the **contract** for takctl (CLI + web backend + UI assets).

## Scope

takctl includes:
- Python CLI
- FastAPI web backend (serves API + static UI)
- Static UI assets (no bundler requirement)
- Supporting helpers for onboarding-related privileged operations (e.g. UserManager integration)


## Web scope and onboarding ownership (AUTHORITATIVE)

takctl-web is **not** a replacement for the TAK Server (Marti) administrative UI.

takctl-web has a deliberately limited and additive scope.

### takctl-web does NOT own

takctl-web must not re-implement or duplicate:

- User identity systems
- Group definitions or group membership logic
- Authentication policy
- Authorization semantics
- Certificate authority policy
- Long-term certificate lifecycle management

These remain authoritative in:
- TAK Server (Marti)
- Backing identity providers (File, LDAP, AD, etc)

takctl-web must treat users and groups as **external state**.

---

### takctl-web DOES own

takctl-web owns **onboarding state and onboarding artifacts**, not identity.

Specifically, takctl-web is responsible for:

- Discovering users from authoritative sources
- Tracking onboarding readiness and status per user
- Generating onboarding packages
- Generating QR codes and enrollment links
- Managing onboarding package composition:
  - plugins
  - configuration
  - maps
  - profiles
- Exposing onboarding flows via Web UI and API
- LLM-backed onboarding and operational views

This ownership is additive and non-destructive.

---

### Relationship with Marti UI

Marti remains the authoritative UI for:

- User creation
- Group assignment
- Role management
- Certificate inspection
- Security and authentication configuration

takctl-web may:

- Redirect or deep-link operators to Marti
- Observe resulting state
- Act on that state to generate onboarding artifacts

takctl-web must not fork, shadow, or replicate Marti’s user/group UI.

---

### User discovery model

takctl-web must support **pluggable user backends**, including:

- UserAuthenticationFile.xml
- Marti-backed user listings (if/when available)
- LDAP / AD-backed identity sources
- Headless provisioning inputs (CSV / Excel)

takctl-web must not assume how users were created.

---

### Supported onboarding flows

takctl-web must support multiple onboarding scenarios:

1. **Auto-enrollment (credentials-based)**
   - User receives username/password and server info
   - Client performs auto-enrollment
   - Correct onboarding package is generated and served

2. **Auto-enrollment (QR-based)**
   - QR code embeds enrollment information
   - Client auto-enrolls
   - Package auto-download or follow-up fetch

3. **Browser-assisted onboarding**
   - QR code opens a browser enrollment page
   - User downloads onboarding packages manually

4. **Manual enrollment**
   - User logs in to an onboarding endpoint
   - Downloads packages explicitly

All flows are first-class and supported.

---

### Onboarding state model

takctl-web maintains an internal onboarding state per user, including:

- External user identifier
- Callsign (if available)
- Package generation status
- Package version or hash
- Generation timestamp
- Download events (best-effort)
- Target client type (ATAK / iTAK / WinTAK)

This state is **derived and auxiliary**.

Loss of onboarding state must not affect TAK Server correctness.

## Deployment model

Runtime is authoritative:
- `/opt/tak/tools/takctl`

Source is staging:
- `/opt/taks/takctl`

Convergence is performed by tak-installer (rsync/deploy step).
Manual edits in runtime are transitional only.

## Web mounting

Public mount:
- `https://<FQDN>/takctl/`

Backend:
- `takctl-web.service` binds to `127.0.0.1:8080`

Mount rule:
- UI must work under a prefix (`/takctl/`).
- `index.html` must include `<base href="/takctl/">`.
- API calls should be relative (e.g. `api/health`) so they resolve under the base.

## Privilege model

Reads:
- CoreConfig.xml and UserAuthenticationFile.xml (as referenced by CoreConfig)
- DB access is read-only by default unless explicitly documented otherwise.

Writes:
- Must be mediated via controlled helper(s) + sudoers-limited scope.
- No direct root logic inside the web backend.

## API contract (minimal)

At minimum:
- `/api/health` returns backend health
- `/openapi.json` returns OpenAPI spec

Additional endpoints are allowed, but must be stable once published.

## Failure semantics

takctl must fail loudly and clearly:
- Missing CoreConfig.xml
- CoreConfig parse errors
- Missing auth file references
- Missing UserAuthenticationFile.xml
- User not found

No silent fallbacks.

### API paths (internal vs public)

Internal (loopback, uvicorn):
- `http://127.0.0.1:8080/api/*`

Public (via nginx mount prefix):
- `https://<FQDN>/takctl/api/*`

Versioned API may be exposed under:
- `/api/v1/*`


