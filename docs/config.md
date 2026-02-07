takctl Configuration Model (Authoritative)

This document explains how configuration is loaded and used in takctl, for both CLI and Web (systemd) execution.

If you remember nothing else, remember this:

Never instantiate Config() directly in runtime code.
Always use load_config() unless you very intentionally want defaults only.

Overview

takctl configuration is resolved from three layers, in strict precedence order:

Environment variables (TAKCTL_*)

Config files (takctl.conf, secrets/db.env)

Built-in defaults (safe only for CLI / development)

The Web UI (takctl-web, systemd-run) relies on layers 1 and 2.
Defaults alone are not sufficient for production.

The One True Entry Point: load_config()
✅ Correct
from takctl.config import load_config

cfg = load_config()

❌ Incorrect (will break Web / DB / CRL)
from takctl.config import Config

cfg = Config()   # DO NOT DO THIS in runtime code

Why?

Config() does not load:

environment variables

takctl.conf

secrets/db.env

load_config() does all of the above, in the correct order

Configuration Resolution Order
0) Early DB Secrets Load (Web-safe)

Before anything else, load_config() loads:

/opt/tak/tools/takctl/secrets/db.env


Format:

TAKCTL_DB_HOST=127.0.0.1
TAKCTL_DB_PORT=5432
TAKCTL_DB_NAME=cot
TAKCTL_DB_USER=takctl_crl_ro
TAKCTL_DB_PASSWORD=********


Notes:

Missing file is allowed

Existing environment variables are not overwritten

This is required for psycopg2 mode under systemd

1) Environment Variables (Highest Priority)

Any variable named:

TAKCTL_<NAME>


Overrides everything else.

Examples:

TAKCTL_DB_PASSWORD=...
TAKCTL_CONFIG=/custom/path/takctl.conf

2) Config File (takctl.conf)

Default path:

/opt/tak/tools/takctl/takctl.conf


Example (actual working minimum):

[takctl]
db_mode = psycopg2

db_host = 127.0.0.1
db_port = 5432
db_name = cot
db_user = takctl_crl_ro
db_password = ********


Notes:

Section headers ([takctl]) are ignored but allowed

Keys are read as lowercase

Empty values are treated as unset

3) Defaults (Last Resort)

Defined in Config dataclass:

db_mode = "psql_sudo"
db_host = "127.0.0.1"
db_port = 5432
db_name = "cot"
db_user = "postgres"
db_password = None


⚠️ Defaults are not safe for Web/UI usage

They exist mainly for:

legacy CLI behavior

local debugging

explicit psql_sudo mode

Database Modes Explained
psql_sudo (Legacy)

Uses: sudo -u <user> psql

No password required

Requires:

local trust auth

interactive shell or sudo permissions

❌ Not suitable for Web / systemd

psycopg2 (Required for Web)

Uses TCP connection

Requires:

username

password

Works under systemd

Used by:

Web UI

FastAPI backend

LLM tools

Guardrail enforced:

If you try to use psycopg2 without a password, takctl will fail fast with:

ValueError: psycopg2 requires db_password


This is intentional and prevents silent misconfiguration.

Why the DB Broke Earlier (Post-Mortem)

The failure mode was:

Runtime code instantiated Config() directly

That skipped:

secrets/db.env

takctl.conf

Defaults kicked in:

db_user = postgres
db_password = None


psycopg2 attempted password auth → 💥

Fix:

Replace all runtime Config() usage with load_config()

Add a validation guard so it never happens silently again

Rules Going Forward (Non-Negotiable)
✅ DO

Use load_config() in:

Web backend

Services

Anything touching DB, filesystem, systemd, OpenSSL

Put secrets in:

secrets/db.env

Treat takctl.conf as runtime-authoritative

❌ DO NOT

Instantiate Config() directly in runtime code

Rely on defaults for Web/UI

Parse CoreConfig.xml for DB credentials (unless explicitly documented)

Quick Sanity Check (Runtime)
/opt/tak/tools/takctl/.venv/bin/python - <<'PY'
from takctl.config import load_config
cfg = load_config()
print(cfg.db_mode, cfg.db_user, bool(cfg.db_password))
PY


Expected:

psycopg2 takctl_crl_ro True

Summary (TL;DR)

load_config() is mandatory

Defaults are unsafe

psycopg2 requires credentials

Secrets live in secrets/db.env

If DB breaks, check how Config was constructed first
