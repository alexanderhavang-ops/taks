> [!IMPORTANT] Non-authoritative
> This document is **background**. For authoritative contracts, start at:
> - docs/contracts/README.md

# TAK Installer (tak-installer)

## Certificate handling

The installer does not decide which certificate to use.

It:
- Installs certificates provided by orchestrator
- Verifies permissions and layout
- Reloads nginx safely
- Exposes verification data when possible

All policy decisions live above the installer layer.

## takctl runtime deployment

The installer includes a dedicated action:

- Action ID: takctl-runtime
- Purpose: Converge takctl source to runtime

### Behavior
- Executes /opt/taks/tak-installer/scripts/deploy-takctl-runtime
- Uses rsync with explicit excludes
- Supports --dry-run and real apply

### Order in plan
This action must run before:
- systemd-takctl-web

This guarantees that:
- Code is deployed
- Then systemd restarts the web backend against the updated code

## Action interface contract

All tak-installer actions must follow a strict discovery and execution contract.

### Discovery
- Actions are discovered from tak_installer/actions/*.py
- Each module must export a global named ACTION
- ACTION must define a unique ID string

### Execution interface
Each action must implement:
- inspect(self, ctx) -> int
- apply(self, ctx) -> int

## Plan files (*.action)

Plan files define execution order, not behavior.

- Filename controls ordering
- File contents must be the action ID
- Empty lines and comments are ignored

Example:

05-takctl-runtime.action
takctl-runtime

## Required environment variables

tak-installer is intentionally non-interactive.

### FQDN
Provide one of:
- FQDN (preferred)
- TAKS_FQDN (fallback)

Example:

export FQDN=46hvbat.tak-hv-sandbox.se
./tak-installer/tak-installer apply --dry-run
