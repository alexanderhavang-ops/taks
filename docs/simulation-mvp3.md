# Simulator: monitoring and recipient state

ChatGPT supplies explicit decisions. The node owns persistent connections,
movement interpolation, supplied timers, recipient inboxes and knowledge.
It has no planner, inference loop or autonomous military decision model.

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
- Incoming GeoChat addresses determine recipient delivery. A message never
  executes MCP commands by itself. A currently active ChatGPT reasoning session
  reads the recipient event and chooses its response or other explicit action.
  Finishing a chat turn does not leave ChatGPT continuously reasoning on the node.

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

## Transport and behaviour work remaining

GeoChat is implemented. XMPP and Mumble are not yet simulated transports.
Before enabling them, use the normal TAKS onboarding identity and room/channel
membership; preserve credentials privately and measure each transport separately.
XMPP needs one authenticated stream per actor with the assigned conference
memberships. Mumble needs authenticated identities, explicit channel membership,
codec support and rate-limited PTT playback. Generate and queue a few audio clips,
rather than synthesizing continuously or starting a process per actor.

Background movement is last. When added it consists of explicit, bounded patrol,
errand and vehicle-route timelines prepared by ChatGPT, using mapped roads and
paths. Stationary presence alone does not imply such activity is implemented.

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
