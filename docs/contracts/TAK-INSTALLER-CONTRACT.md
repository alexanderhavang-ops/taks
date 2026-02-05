# tak-installer Contract (Authoritative)

This document is the **contract** for tak-installer (node converger).

## Inputs

tak-installer is intentionally non-interactive.  
Required inputs:
- `FQDN` (preferred) or `TAKS_FQDN` (fallback)

## Action model

- Actions are python modules under `tak_installer/actions/*.py`
- Each exports `ACTION` with a unique `ID`
- Each action implements:
  - `inspect(ctx)` for dry-run
  - `apply(ctx)` for real apply

