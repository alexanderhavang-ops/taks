# Chat-controlled simulation MVP

One persistent asyncio daemon runs on the TAK node. It owns distinct mTLS
client sessions; TAK Server routes their CoT to ATAK observer clients. There
is no model, planner, or per-person process. The separate map and reference
tools provide context to ChatGPT, which submits explicit actions.

The MVP provisions eight dedicated non-admin `sim-mvp-*` identities. It can
create a synthetic group, publish one HQ/member marker per identity, move
the group through explicit geographic waypoints, stop movement, deactivate
presence, and send a GeoChat message. It does not yet implement TAKS ORBAT
import, XMPP, Mumble, tactical behaviors, or battalion-scale certification.

## Controls

Dedicated tools: `taks_node_simulation_read`, `taks_node_simulation_control`,
and `taks_node_reference_docs`. For clients with a cached tool catalog,
the existing `taks_node_service_read/write` route can expose the same fixed
operations using services `simulation` and `reference_docs`.

Read `simulation/status` before a mutation. All mutations require
`request_id` (1..32 safe characters), `expected_revision`, and `unit_id`.
Retries use identical arguments and are deduplicated within a bounded 512
request history. A reused ID with different arguments is rejected.

Example create arguments:

```json
{"request_id":"create-demo-1","expected_revision":0,"unit_id":"demo",
 "callsign":"SIM-DEMO","count":4,"position":{"lat":55.715,"lon":13.215}}
```

Move operation arguments add `path` (1..100 destination waypoints, each
`{"lat":...,"lon":...}`) and `duration_s`. The current position is prepended.
Each member follows the same path with its initial offset. These offsets
are a simple demonstration, not terrain-aware navigation or formation AI.
Coordinates are authoritative; no map service is called by the daemon.

`stop` holds the current position and retains live presence. `deactivate`
closes that unit's sessions; old ATAK tracks become stale after 90 seconds.
`chat` accepts `message`, optional `entity_id`, and optional `target_uid`
and `target_callsign` (default All Chat Rooms). Delivery means a local TLS
write, not an ATAK acknowledgment. Retries never automatically duplicate
chat. A crash during a write can leave delivery unknown.

Movement advances approximately every ten seconds and on control calls.
Snapshots persist action progress atomically. Restart resumes remaining
movement from the saved position; it does not advance through downtime or
replay historical chat. Takeover/multiple daemon instances are not supported.

Status includes current state, recent events, session health, and the most
recent exercise positions received back through TAK fan-out. This is wire
evidence, not proof that a particular ATAK device rendered a marker.

## Reference documents

All six existing Martine reference operations are available: catalog,
keyword search, semantic search, chunk context, section list, section read.
An empty store returns `state: empty` without importing a model or starting
a retrieval worker. Nonempty retrieval uses Martine's dependency environment
with a fixed allowlist and bounded execution. Document IDs are validated
against the active registry. Page/section metadata is preserved.

## Deployment and validation

Use the cattle workflow for taklabs. The DevOps release extension is maintained
in `alexanderhavang-ops/devops-mcp`, branch `codex/taks-simulation-release`.
Its named MCP tools expose release staging/status; the existing command entry
point also accepts the exact `taks-release` subcommands below when the host's
tool catalog is cached. Arbitrary shell remains disabled.

1. `taks-release stage SHA` stages reviewed MVP overlays over the currently
   installed TAKS source, preserving existing source changes. It records the
   overlay commit and enables simulation only in taklabs bootstrap config.
2. `taks-release backup taklabs.aws.tak-hv-sandbox.se confirm` creates a complete
   backup. Poll the operation ID. Credentials/archive contents stay on the server.
3. `taks-release restore taklabs BACKUP_ID confirm` verifies and selects restore.
4. `taks-release bundle taklabs confirm` builds the replacement bundle.
5. `taks-release verify taklabs` verifies the actual archive contains all MVP
   modules, the source commit marker, and explicit simulation enablement.
6. After preview/dry-run, use `taks-release shutdown NODE EXPECTED_INSTANCE_ID
   BACKUP_ID confirm`. The existing lifecycle guard requires a verified complete
   backup and exact node/instance matching before termination.
7. `taks-release launch taklabs confirm` launches a fresh t3.medium. Poll operation
   status and node installation/health before using the exercise tools.

Poll any asynchronous operation using `taks-release poll OPERATION_ID`.
Node certificates, users and documents are restored through the normal backup
pipeline. The `simulation-runtime` installer action runs from the bundle's source
without downloading code on the node. It starts an empty exercise daemon; creating
the test group is a separate explicit MCP action after health verification.

`tools/deploy-simulation-mvp.py --commit SHA` installs only the explicit MVP
modules, an additive node Business MCP hook, dedicated identities, and its
systemd unit. Runtime state/config of other services is preserved; changed
files are backed up. `/opt/tak/simulation` contains node-local state and
credentials, never returned through MCP. A private-CA verified server leaf
is pinned to accommodate older TAK certificates without DNS SANs. Replacing
the server certificate requires an explicit installer rerun to refresh it.

For existing orchestration installations, apply the reviewed additive hook
and route allowlist changes; do not replace a drifted runtime wholesale.
The restricted DevOps adapter in `tools/devops/simulation_ops.py` provides
fixed `taks-mvp inspect/deploy/poll` operations while keeping arbitrary shell
disabled. Deploy accepts only a full SHA of the fixed public TAKS repository.

Run `PYTHONPATH=takctl python -m unittest discover -s takctl/tests -p test_simulation_mvp.py -v`.
Tests cover movement, offsets, waypoints, stop, replay recovery, deduplication,
validation, empty documents, extension boundaries, mTLS fan-out, and framed
control. Sandboxes prohibiting AF_UNIX use TCP for that test handler only;
the deployed daemon always uses its permission-restricted Unix socket.

The service has a 256 MiB memory limit and an eight-identity initial pool.
400+ sessions, fan-out, TLS overhead and long-running memory usage still
require a separate load test before increasing the configured limits.
