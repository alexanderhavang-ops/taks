# Chat-controlled simulation MVP2

ChatGPT chooses coordinates and actions. The node runs one asyncio daemon
with a distinct mTLS certificate/session per active entity. ATAK observes
the CoT distributed by TAK Server. No inference or tactical planner runs
on the node. MVP2 does not claim 400-client load validation: the current
installer provisions eight identities by default (configurable up to 16).

## Map context, separate from execution

`taks_node_map_read(node_id, operation, arguments)` exposes:

| Operation | Arguments | Result |
| --- | --- | --- |
| `config` | none | Supported operations, query bounds and cache policy |
| `area` | `center:{lat,lon}`, optional `radius_m`, `kinds`, `limit`, `offset`, `query` | Paginated OSM features with tags, names and GeoJSON geometry; feature counts |
| `feature` | `feature_id` such as `way/123` | A specific mapped object |
| `route` | `start:{lat,lon}`, `end:{lat,lon}`, optional `speed_mps` | A pedestrian graph path, distance, duration, way IDs and endpoint snap distances |

With a cached client tool catalog, use the existing service read tool:
`service=simulation`, `operation=map_area/map_feature/map_route/map_config`.
The geometry reader runs in the node's Business MCP web runtime, outside the
simulation daemon; there is no map query per movement tick. The orchestrator
forwards bounded responses rather than importing an entire regional map.

OSM data comes from configured Overpass endpoints. Queries cover 100–1500m
and responses are capped at 4MiB; four query results can be cached for ten
minutes. Area results paginate, and response budgets never silently truncate
individual feature geometry. Relations without assembled geometry are
explicitly incomplete. Every result identifies attribution, fetch time and
OSM database time where supplied. No map download/import is required.

The walking lookup uses shared OSM node IDs and distance-weighted graph
search. It applies basic `foot`/`access` tags and `oneway:foot`; it does not
treat a public OSRM driving backend as a pedestrian router. A disconnected
graph returns an error instead of a straight-line substitute. These are
mapped candidate paths: barriers, conditional access, temporary closures,
snap connectors and interiors remain unverified. It does not infer cover,
defensive positions, line of sight or terrain height. See the OSM
[access model](https://wiki.openstreetmap.org/wiki/Key:access).

Routes retain original graph vertices. `single_move_compatible` indicates
whether the returned path fits the daemon's 100-destination limit. Longer
routes require shorter legs. A map read never issues movement. Lat/lon
remains authoritative; ChatGPT inspects the result and submits the path.

## Generic controls

Read `view=capabilities` through `taks_node_simulation_read`, or service read
`simulation/capabilities`, for operation names, argument contracts and limits.
All writes use `request_id` and the current `expected_revision`. Unit writes
also require `unit_id`; global `pause` and `resume` omit it.

| Control | Behavior |
| --- | --- |
| `create` with `members` | Optional JSON profile per entity, including explicit positions |
| `entity_move`, `entity_stop` | Independent paths and stops; units retain their UIDs |
| `batch` | 1–32 state changes committed together; no formation semantics |
| `entity_patch` | Health, callsign, role, readiness, group, vehicle link, platform, CoT type and bounded metadata |
| `unit_patch` | TAKS ORBAT reference and unit metadata |
| `marker_put`, `marker_remove` | Persistent exercise objects with explicit symbols; no new TLS clients |
| `cot_send`, `cot_remove` | Validated unit-scoped custom XML, optionally refreshed every tick |
| `chat` | Per-identity GeoChat, with optional destination |
| `pause`, `resume` | Freeze/resume movement and exercise clock while keeping CoT sessions live |
| `schedule_put`, `schedule_cancel` | Supply or cancel an explicit future unit action |

The [example profile](../examples/simulation/group-profile.json) can be merged
with `unit_id`, a chosen `position`, `request_id`, and `expected_revision` for
`create`. It is exercise data, not a replacement ORBAT. TAKS remains the ORBAT
authority; the reference and descriptive metadata are local exercise state.
`metadata` is a replacement JSON object capped at 2KiB per entity/unit.
Leader personality, fuel, capacity and readiness are supplied facts; the
daemon does not generate decisions from them. `group_id` and `vehicle_id`
are descriptive links: moving a vehicle does not automatically move riders.

## Explicit timeline and recovery

`schedule_put` takes `schedule_id`, `delay_s` (10–86400), `operation`, and
`arguments`. The nested arguments belong to that unit and omit request/revision.
The action is validated when scheduled and again when executed. Maximum 64
rows, including completed history. It supports movement, status, map-object
updates, chat and atomic state batches, but cannot schedule more schedules.
There is no target-side scenario authoring, reasoning or planning loop.

Timers use the exercise clock. Pause and node downtime do not consume remaining
duration. Execution is approximately ten-second resolution. Before any action
is attempted, its state is persisted as `attempt_pending`. A crash can leave
that state uncertain: it is never automatically retried, especially for chat.
Completed/failed actions retain their results for review. A completed command
does not imply an ATAK device acknowledged a network message.

Status includes the timeline, pause/clock state, metadata, markers, custom CoT,
connection health, runtime memory peak, and objects received back through TAK.
A bounded volatile inbox captures the last 100 GeoChat messages observed by
the simulated connections and deduplicates server fan-out. Inbox and network
observations reset on daemon restart; movement, timeline and entity state persist.
`view=export` returns the exercise state without transport keys/configuration;
this is runtime data and must not be committed to a public repository.

XMPP identities, Mumble audio/PTT, automatic mounted movement, regional offline
map imports and production-scale client load testing remain outside MVP2.

## Validation and release

Run the simulation suites with
`PYTHONPATH=takctl python -m unittest discover -s takctl/tests -p 'test_simulation_mvp*.py'`.
They cover atomic individual paths, persistence, certificate transport, GeoChat
fan-out, pause/resume, explicit timers, crash uncertainty, profile validation,
map input boundaries, graph connectivity, access-tag filtering and pagination.
Use the existing guarded DevOps cattle release workflow described in
[MVP deployment](simulation-mvp.md). The source overlay and installer both
include the map module. Runtime exercise exports/seeds stay outside git.
