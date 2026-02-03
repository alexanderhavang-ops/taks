# Orchestrator Contract (Authoritative)

This document is the **contract** for the TAKS orchestrator (control plane).

## Scope

The orchestrator:
- does not run TAK itself
- owns control-plane workflows:
  - node state tracking
  - cert inventory / lifecycle
  - offline artifact workflows
  - (future) node launch automation (AWS first)

## DNS / naming

Canonical DNS contract is documented in:
- `docs/DNS.md` (authoritative for naming)

## Node state model

Each node tracks (independent axes):

Reachability:
- reachable (green)
- unknown (yellow)
- offline (red/gray)

Certificate status:
- up-to-date
- pending deployment
- expiring/expired
- unknown installed state

## Certificate lifecycle model

Cert deployment states must be explicit (no inference), e.g.:
- ISSUED
- AVAILABLE_FOR_DOWNLOAD
- DOWNLOADED
- INSTALLED_UNVERIFIED
- INSTALLED_VERIFIED
- SUPERSEDED
- REVOKED

Online nodes may support automatic verification via reported serial/fingerprint.

Offline nodes use operator-driven workflows with explicit tracking.

## API contract

Orchestrator API should be versioned:
- `/api/v1/*`

Unversioned endpoints are legacy and must be treated as temporary.

OpenAPI must be served at:
- `/openapi.json`
