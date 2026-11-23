# Simulator: monitoring and recipient state

ChatGPT supplies explicit decisions. The node owns persistent connections,
movement interpolation, supplied timers, recipient inboxes and knowledge.
The exercise-wide reasoning loop supplies plans. An optional node-local
Agents SDK handler interprets direct orders for one actor.

## Delivered foundation

- The same bounded `process_sample`, `memory_read`, and `vmstat_sample` kernel
  sampler on the node and orchestrator. CPU values are measured over an interval;
  host percentages cover all logical CPUs, process 100% means one logical CPU.
  No process arguments, environment, unrestricted commands or arbitrary paths.
- An inactive eight-person group factory with fictional full names, authoritative
  TAKS identity grammar, designation, colour and group metadata. The installer
  updates dedicated TAKS-backed LDAP accounts with encoded display-name fields.
- Echelon SIDCs on group/platoon/company/battalion HQ annotations, on both
  `__milsym` and `__milicon`; ATAK client rendering still requires visual checking.
- SQLite recipient journal: message bodies stored once, recipient references
  separate, 10,000-message retention with cursor-gap signalling. Actor knowledge
  is at most 8KiB, explicitly written and independently versioned. SQLite cache
  is bounded. Consistent actor snapshots travel in the ordinary state backup.
- `simulation/actor` reads one actor's own state, knowledge and inbox.
  `simulation/events` reads a durable cursor, optionally scoped to `entity_id`.
  Omission means the explicit god view. `knowledge_put` uses `entity_id`,
  `request_id`, `expected_actor_revision`, `knowledge`; it does not use the world
  revision. These tools preserve data isolation; ChatGPT must also respect the
  chosen perspective when reasoning, since its god tools remain omniscient.
- The command view supplies the actor's squad-to-battalion reporting line and
  direct subordinate echelons. Use `command_configure` to record commander or
  deputy handovers. Roster appointments give addresses and reporting lines.
  Positions and other actors' inboxes stay outside this view.

## Order workflow for the next exercise

The operator addresses the highest commander appropriate to the exercise size.
ChatGPT reasons from that actor's inbox and knowledge, supplies an explicit
preparation delay, and sends heads-up messages through GeoChat. In a larger
roster, staff roles collect and develop their own situation reports and proposals;
messages carry those reports back to command. Command communicates orders down
the hierarchy, with recipient acknowledgements and preparation time at each step.
Readiness, experience, communication availability and workload are descriptive
inputs to ChatGPT's decisions. They are not a hidden target-side planner.

A subordinate knows what it observes or receives, with report source and time.
A unit does not automatically learn every god-view position or casualty.
Global time, authoritative latitude/longitude and execution status remain in
the world model. Actor beliefs can be incomplete, wrong or stale. ChatGPT writes
observations into the relevant actor's knowledge explicitly.

## Looping routes, recurring actions, and markers

Use `background_put` with `unit_id` to move a formation at its stored member
offsets. Add `entity_id` to move one actor. Supply up to 512 waypoints,
each with `position`, `travel_s`, and `wait_s`. With `repeat: true`, the last
waypoint must return to the start. The route repeats until paused, removed, or
superseded by a foreground move. The daemon saves route progress and resumes
from that point after restart. A paused exercise freezes movement and its
schedule clock.

Use `schedule_put` with `delay_s` for the first action and optional
`interval_s` (10–86,400 seconds) for recurring actions. Child arguments use
the same `unit_id` and omit request and revision fields. Actions include
`chat`, `xmpp_chat`, `mumble_ptt`, `marker_put`, and `marker_remove`.
Mumble plays an existing clip over the actor's configured connection and
channel. Inspect `last_occurrence` for the outcome and `due_clock_s` for the
next deadline, or use `schedule_cancel` to end the series. A delayed scheduler
skips missed intervals. After a restart, an uncertain send is recorded and the
series continues with a fresh request ID at its next deadline.

`marker_put` defaults to a 300-second wall-clock TTL. Set `ttl_s` (1–86,400
seconds) to choose a different lifetime. The daemon stops publishing expired
markers, removes them from saved state, and caps each CoT stale timestamp at the
expiry. The wall-clock TTL still applies during pause or downtime. Only
deliberately static markers such as ORBAT headquarters use `ttl_s: null`.
`marker_remove` releases the marker slot and sends a CoT deletion over the
owner's connection when available. Client receipt is unconfirmed, so the last
advertised stale timestamp is the fallback.

## Health, supplies, and rotation

Set actor `sustainment` in `create.members` or through `entity_patch`.
It includes `health_pct`, `satiation_pct`, `hydration_pct`, carried
`rations` and `water_ml`, and `ammunition` and `equipment` maps of item IDs
to counts. Set `duty_status` to track the current activity, such as
`on-duty`, `meal`, or `resting`. A patch changes only the supplied fields. An inventory map replaces
that category, so an empty map clears it. Omitted values on an existing actor
are unknown. Read an individual through `actor`, or scan actors through the
paged `status` response.

The reasoning loop sets how often each actor needs to eat and drink in an
exercise day. Build in that many reachable stops, stagger them across the
rotation, and leave enough time at each stop for the planned activity. A
waypoint wait provides time for the stop. The reasoning loop accounts for the
elapsed exercise time, checks carried supplies, and records what the actor
actually consumed or received. Use `accounted_through_clock_s` to record the
exercise-clock time covered by a patch and pick up from there after restart.
Use an atomic batch for a supply transfer between actors.

When a stop is missed or supplies run out, the reasoning loop can record
declining needs and health, swap duties, or revise the route. A fatal outcome is
an explicit patch setting `health_pct: 0` and `health_state: "kia"`. Existing
movement rules then keep that actor stationary. Needs and inventory are saved
as given. With no reasoning session active, only previously scheduled patches
run, so the next session accounts for time elapsed since the saved cursor.

## Unattended individual orders

On a configured node, an active fictional actor can respond in the same
transport to a directly addressed XMPP or GeoChat message from a configured
exercise operator. The OpenAI Agents SDK classifies the message. The daemon
validates and applies one individual movement, ration, or water action. A
cardinal move uses an explicit distance in metres, up to 1,000 m. Food and
water orders use what the actor carries. The reply tells the sender what the
actor did or why it was unable to act. Group orders and combat are outside the
handler's scope. Route planning and supply-stop planning stay with the
exercise-wide reasoning loop.

Set space-separated `xmpp_senders` (bare JIDs) or `geochat_senders` (TAK UIDs)
in `config.d/simulation-orders.conf` and keep `openai_api_key` in the
corresponding node secret fragment. `openai_model` is optional. XMPP uses
the authenticated bare JID. GeoChat uses the received CoT sender UID, so
enable that path only on the isolated exercise node with trusted senders.
With empty allowlists the handler stays disabled. The SDK receives the one
message being interpreted, and SDK tracing is disabled.

## Leader orders and local references

An appointed commander can apply a line or two-column arrangement, halt,
follow a separately active unit by exact callsign, or follow the sender's
assigned TAK track. An order can specify the echelon. If the recipient has
multiple appointments and the order omits it, the smallest appointment is
used. Orders apply only to active actors in that echelon. Following holds
position when the operator's track is more than 45 seconds old. An XMPP
operator needs a corresponding TAK device UID for `follow me`.

A named exercise position set is supplied by the exercise designer in each
unit's `metadata.exercise_positions` map. An order such as “Take up defensive
positions” selects the preconfigured `defensive` point for each unit.
The model cannot select new sites or take coordinates from retrieved documents.

The node agent can call the existing local document search for up to two
queries per message. It searches the active, indexed exercise documents, so
newly indexed documents become available during the next order or question.
Retrieved text is considered reference material. The daemon independently
validates the operator, commander appointment, scope and requested action.

## Resource selection

No PostgreSQL tuning or TAK JVM heap overrides were introduced for the exercise.
The simulation service budget is selected by certificate pool and checked against
actual host RAM. Pools <=64 use 128MiB, <=256 use 512MiB, <=640 use 1GiB, and larger
pools use 2GiB; reject a budget exceeding one sixth of host RAM. This is an
execution ceiling, not a claim of actual allocation or a per-client budget.

Only the managed 500-client delivery rule changes: ten seconds for a large
exercise pool, vendor baseline 200 seconds for the small pool. Keep the higher
rules and separate read/DoS settings. No inference is tied to EC2 instance names.

The local `profile-simulation-memory.py` fixture separates world allocations,
SSL-context construction and idle mTLS transports. Its relay is a separate
short-lived test process, excluded from client RSS. It is not a production
TAK capacity test or a memory guarantee for another Python/OpenSSL build.
