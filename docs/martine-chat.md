# Martine chat and access

Node TAKS, orchestrator `/martine`, authenticated local XMPP, and GeoChat use the same `run_once` agent and OpenAI Agents SDK tool definitions. Inference runs on the node. The orchestrator relays authenticated requests to a registered node's Business API; it does not require the DevOps gateway or run a second model stack.

The UI exchanges asynchronous job IDs and account-scoped history, never unrestricted agent traces. Sessions include unit, canonical account, role, and conversation. LDAP `TAKS_ADMIN` membership is checked on each authenticated request and before execution. Roles and account identity are never taken from model arguments, callsigns, XMPP resources, or browser request bodies. XMPP derives the account from the authenticated local-domain JID. GeoChat payload identity is currently unverified and gets general help/reference tools only; private diagnostics require signed-in web or authenticated XMPP.

Normal users can inspect their own onboarding and attributed connection events, and send configured onboarding packages to their own attributed devices. They cannot read arbitrary logs or other accounts. Admins additionally receive allowlisted product diagnostics, bounded credential-redacted log tails, fixed file metadata, Marti GET operations, and native LDAP/Mumble/Openfire business reads. No chat tool deploys, executes shell, writes arbitrary files, or approves administrative changes. Native business writes create a five-minute, account-bound proposal that an admin must explicitly confirm in the UI; replay and cross-account confirmation are rejected.

The node's other administrative APIs also require a fresh admin role. Public health/login and opaque soldier-card links retain their existing access rules. Business internal requests use a fixed loopback bearer; loopback by itself is insufficient.

Future state backups include consistent SQLite snapshots of chat jobs/actions and Agents SDK sessions. OpenAI secrets stay server-side. Logs and tool outputs are redacted before they reach chat; raw traces are not exposed through the web chat API.

## Validation

Deterministic tests run the real Agents SDK Runner and MCP server with a local model fixture, covering tool round trips, session isolation, denied cross-account diagnostics and raw logs, and proposal-only mutation. Separate HTTP tests cover UI identity forgery, normal/admin API isolation, internal bearer checks, and orchestrator node-bound sessions. These tests do not call OpenAI or prove live network delivery; deploy checks must additionally verify live inference and the target services.
