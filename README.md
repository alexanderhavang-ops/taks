TAKS / takctl
OVERVIEW
TAKS is a clean, reproducible control plane for operating one or many TAK Server instances,
from a single standalone node to a federated hierarchy or cluster, without embedding site-specific
or secret material in git.
While this project is being developed and validated in the context of the Swedish Hemvarnet,
it is not Hemvarnet-specific.
TAKS can be used by any organization that wants to deploy and operate:
•	a single TAK Server
•	multiple TAK Servers
•	or a federated TAK Server topology
Across airgapped, cloud, or hybrid environments.
A first-class goal is to combine traditional TAK administration with GenAI-assisted operational
views, making the system useful not only for administrators, but also for operators.
CORE IDEA
Git describes intent. Runtime holds state. Privilege is explicit.
Git contains how things should be.
Runtime reflects what is currently running.
No secrets, certs, hostnames, or organizational names live in git.
Read-only operations must always work.
Privileged operations are centralized and auditable.
HIGH-LEVEL GOALS
1.	Build a 100% operational TAK environment suitable for real-world use.
2.	Support any organization, from single-node deployments to federated clusters.
3.	Develop and validate the system in a Swedish Hemvarnet context, without hard-coding it.
4.	Put GenAI-assisted operational views first:
o	Tactical Operations
o	Security Operations
o	System Health and Resilience
5.	Support airgapped, AWS-hosted, and hybrid deployments.
6.	Provide a master orchestrator node with a Web UI to:
o	spawn battalions, companies, or generic organizational units
o	bootstrap nodes via cloud-init so they become immediately actionable
o	manage lifecycle: install, update, health, rotate, retire
7.	On every TAK Server node, provide a consistent ops surface:
o	TAK Server (target version: TakServer 5.6)
o	nginx wiring for enrollment and web entrypoints
o	takctl Web UI for users, certs, clients, CRLs
o	GenAI views for Tactical Ops, Security Ops, and System Health
8.	Keep the repository public-safe and sanitizable.
9.	Make installers robust and deterministic (cloud-init first).
REPOSITORY VS RUNTIME (NON-NEGOTIABLE SPLIT)
Source (git, canonical)
Path: /opt/taks
This is the canonical source of truth. Intended to be public or sanitizable.
Contains no secrets, certificates, CRLs, hostnames, or battalion/organization names.
Key directories:
takctl/ Python package (CLI + WebUI backend + services)
tak-installer/ TAK node installer (cloud-init driven)
orchestrator-installer/ master orchestration node installer
infra/ generic systemd units, nginx templates, etc.
Runtime (mutable, operational)
Path: /opt/tak/tools/takctl
This is what systemd actually runs. It contains:
•	Python virtualenv (.venv)
•	deployed copy of takctl
•	logs, caches, runtime artifacts
•	active config file: /opt/tak/tools/takctl/takctl.conf
Drift between source and runtime can and will happen unless an explicit deploy/sync step is performed.
This is intentional and acknowledged.
TAKCTL EXECUTION MODEL
CLI
Entry point: /usr/local/bin/takctl
Wrapper executes: /opt/tak/tools/takctl/.venv/bin/python -m takctl.main
The CLI always runs against the runtime tree, never directly from git.
Web UI
systemd unit: takctl-web.service
Runs via uvicorn: uvicorn takctl.webapp:app
Binds to 127.0.0.1:8080
Reverse-proxied by nginx if exposed externally.
The Web UI and CLI share the same backend logic.
CONFIGURATION MODEL
Active configuration (site-specific, not secret):
/opt/tak/tools/takctl/takctl.conf (INI-style key = value)
Rendered by installers, never committed to git.
Secrets (DB passwords, PKCS#12 passphrases, etc.) are provided via environment variables
or separate root-readable files.
Example configuration (git):
takctl/takctl.conf.example
Config loader guarantees:
•	load must never fail due to missing privileged helpers, missing ops broker, or missing sudo permissions
•	TAKCTL_* environment variables override file values
•	validation belongs in command execution paths, not global load
PRIVILEGED OPERATIONS (CRITICAL DESIGN)
Intended architecture: all privileged actions converge on one auditable path:
•	CRL signing
•	user create/delete
•	group membership changes
•	systemd restarts
Goals: no scattered sudo rules, no multiple setuid helpers, clear privilege boundary.
Ops broker (planned):
•	systemd unit: takctl-opsd.service
•	dedicated privileged user
•	Unix socket interface (example: /run/takctl/opsd.sock)
•	current status: unit file exists; broker binary does not; not implemented yet
Legacy helper (current reality):
•	a root-readable helper script exists for CRL signing
•	generates CRLs to stdout; may revoke certificates passed via stdin
•	must not be required at config-load time
•	temporary fallback or deprecated once broker exists
INSTALLERS
Installers are first-class citizens. They must be sufficient to:
•	bring up a new TAK node or orchestrator node
•	create runtime directories and venvs
•	render takctl.conf
•	install and enable systemd units
•	wire nginx and enrollment endpoints
Git must never assume a pre-existing battalion, a specific hostname, or existing cert material.
EXPLICIT NON-GOALS
Not a full TAK replacement.
Not a UI-heavy admin monolith.
Not a certificate authority by itself.
Not battalion-specific software.
TAKS is a control plane, not an all-in-one system.
CURRENT OPEN DECISION (BLOCKING)
Primary architectural decision:
Implement the privileged ops broker now, or formally support the legacy helper as a temporary fallback?
Subsequent decisions depend on resolving this.
HOW TO REASON ABOUT THIS REPOSITORY
Git shows how things should be.
Runtime shows what is currently running.
Privilege is explicit, never implicit.
Failures should be local and loud, not at import time.
This document is the map. The code fills in the terrain.


