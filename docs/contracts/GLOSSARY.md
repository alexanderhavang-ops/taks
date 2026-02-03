# Glossary (Authoritative)

This glossary defines terms as used by TAKS contracts.

## converge
Bring a system to the desired state by applying deterministic rules/templates.
Convergence should be idempotent: re-running it causes no changes when already correct.

## apply
The real execution that performs convergence (makes changes).

## dry-run
A full execution path that validates inputs and computes what would change,
without making changes.

Dry-run is a safety check, not a simulation.

## plan
An ordered list of actions to run (by action ID), typically expressed as:
- `plans/tak-node.d/*.action`

## action
A single converger unit with:
- an ID
- inspect() for dry-run
- apply() for real apply

## source vs runtime
- source: git/sanitizable repo (e.g. `/opt/taks`)
- runtime: installer-owned authoritative filesystem used by systemd/services (e.g. `/opt/tak`)

## canonical vhost
The single nginx site configuration that is considered authoritative for a host
and is the only enabled site for the relevant ports.

## front door
The client-facing ingress used by ATAK/WebTAK/Marti:
- nginx on 8446 → proxies to internal Marti on 8447

## mounted UI (prefix)
A web UI that is served under a path prefix, e.g.:
- `https://<FQDN>/takctl/`
