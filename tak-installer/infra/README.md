TAKS – INFRASTRUCTURE CONTEXT (NGINX + PORT MODEL)
================================================

PURPOSE
-------
This document captures the intended and current nginx / port wiring model
for TAKS-managed TAK Server nodes.

It exists to prevent re-learning hard-won setup knowledge and to guide
tak-installer apply implementations.

This document is descriptive first, prescriptive second.


HIGH-LEVEL PORT MODEL
--------------------

The following ports are in use on a TAK Server node:

Port 80 (HTTP)
- Purpose: Let's Encrypt HTTP-01 challenge only
- Must be open to the internet
- Scope must be minimal (ACME only)
- No application traffic should be served here

Port 443 (HTTPS)
- Purpose: takctl WebUI and related admin views
- TLS: Let's Encrypt certificate
- nginx reverse proxies to:
    http://127.0.0.1:8080  (takctl FastAPI)
- takctl is served under a path prefix (e.g. /takctl/)

Port 8446 (HTTPS)
- Purpose: Public enrollment and client-facing access
- TLS: Let's Encrypt certificate
- nginx reverse proxies to:
    https://127.0.0.1:8447  (TAK Server Marti API)

- This port serves:
    /Marti/     (TAK API)
    /oauth/     (OAuth endpoints)
    /WebTak/    (WebTAK UI)

- 8446 is the "front door" for clients.
- 8447 is never exposed directly to the internet.


Port 8447 (HTTPS)
- Purpose: Internal TAK Server HTTPS (Marti)
- TLS: Local / internal certs
- clientAuth = false
- Bound by Java (TakServer)
- nginx proxies to this port locally


Port 8089 (TLS)
- Purpose: TAK CoT (Cursor on Target) traffic
- TLS: client certificate authentication required
- No nginx involvement
- Bound directly by TakServer Java process


Additional ports
----------------
- Federation uses additional ports as configured in CoreConfig.xml
- These are out of scope for initial tak-installer work but must be preserved


WEBTAK ACCESS (IMPORTANT, UNFINISHED)
------------------------------------

/WebTak/ is served via nginx on port 8446 and proxied to 8447.

Current state:
- WebTak is reachable via nginx
- Access control is not properly enforced

Desired state (not yet implemented):
- WebTak access should be explicit and permission-based
- nginx must only allow /WebTak/ if the user is authorized for WebTak
- This likely requires nginx auth integration against Marti on 8447

This is a known hard problem and is intentionally deferred.


NGINX CONFIG OWNERSHIP MODEL
----------------------------

The tak-installer is expected to own:

- nginx site configs for:
    * port 80 (ACME only)
    * port 443 (takctl WebUI)
    * port 8446 (enrollment + client access)

- nginx snippets used by those sites

The installer must:
- render configs from templates
- enable/disable sites deterministically
- validate nginx config
- reload nginx idempotently

Nginx core ownership (installer-owned):
- /etc/nginx/nginx.conf
- /etc/nginx/mime.types
- conf.d log_format files may exist; avoid duplicate log_format names


Site-specific values (e.g. FQDN) must be rendered inputs,
never hard-coded in git templates.


CURRENT REALITY (AS OF FEB 2026)
--------------------------------

- nginx is configured manually and works
- configs live under /etc/nginx/sites-available and snippets
- git contains partial templates only
- tak-installer does not yet manage nginx

The next steps are:
1) Capture working configs into git as templates
2) Teach tak-installer apply --dry-run to diff them
3) Enable real apply once diffs are stable


RELATION TO OTHER DOCS
---------------------

- See docs/HANDOFF.txt for overall project state
- See tak-installer/README.md for installer contract
