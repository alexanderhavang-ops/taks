# tak-installer Contract (Authoritative)

This document is the **contract** for tak-installer (node converger).

## Scope

tak-installer is the single entrypoint that converges a TAK node to desired state.

Primary command:
- `tak-installer apply [--dry-run]`

## Inputs

tak-installer is intentionally non-interactive.

Required inputs are provided via:
- environment variables
- root-readable files (for secrets)

Minimum required:
- `FQDN` (preferred) or `TAKS_FQDN` (fallback)

## Action model

- Actions are python modules under `tak_installer/actions/*.py`
- Each exports `ACTION` with a unique `ID`
- Each action implements:
  - `inspect(ctx)` for dry-run
  - `apply(ctx)` for real apply

Plan files:
- `plans/tak-node.d/*.action`
- Filename controls ordering
- File contents are the action ID

## Dry-run semantics

`apply --dry-run`:
- Executes full plan via action inspect()
- Validates env vars and required paths
- Must fail on missing inputs
- Makes no changes

Dry-run is a safety check, not a simulation.

## Ownership / idempotence

Installer owns:
- nginx core + snippets + vhosts relevant to TAK node
- systemd unit convergence
- takctl runtime convergence

Apply must be repeatable:
- no-op if already converged
- only changes when inputs/templates changed
