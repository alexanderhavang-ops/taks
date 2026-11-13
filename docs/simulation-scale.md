# Large exercise rosters

The runtime remains one asyncio process. Each active person has a distinct
client certificate, TLS context and socket. The issuer checks that every
certificate fingerprint in the configured pool is different. Certificate
provisioning happens during the node build; it does not create resident
per-person Python processes.

`simulation_identity_capacity` in the unit's simulation bootstrap fragment
sets the next node's pool, from 1 to 1024. Pools above 64 use a 512MiB daemon
memory ceiling. That ceiling is a guard, not a statement of actual memory use.
The existing four-identity exercise used roughly 27MiB. Measure the target
server after phased activation before making a production capacity claim.

Every simulated connection drains incoming traffic. A shared bounded cache
of 4096 frame digests avoids decoding identical XML hundreds of times when
TAK fans one event out to the whole roster. Per-connection receive counts still
include every framed event. Timestamp/content changes remain distinct events.
The periodic publisher coalesces connection wake-ups and writes owned map
objects together with each identity's presence.

## Read and activate

Status accepts `entity_offset` and `entity_limit` (default 64, maximum 128).
Each unit retains its header and `entity_count`; `entities` contains its slice
of the current page. `pagination` reports the total and next offset. `summary`
reports stored and active people, active units, and connected sessions globally.
Use `simulation_read(view=orbat)` or service read `simulation/orbat` for the
hierarchy, local aliases and unique identities.

Prepared rosters start inactive. `activate` takes the ordinary unit ID, request
ID and expected revision. Activation validates exclusive ownership of every
certificate slot. State batches can activate up to 32 units together. Start
with smaller batches and inspect connections, receive counters and memory.
`deactivate` stops that unit's connections. No activation or routing inference
runs automatically.

During installation, service read `simulation/provisioning` reports certificate
progress without requiring the daemon's Unix socket to be ready.

## Administrative HV example

`takctl.simulation.orbat.build_hv_staging(anchors)` prepares a user-defined
exercise roster. Its inputs are four explicit map annotation anchors, supplied
as runtime data. Its positions use neutral roster-display grids; the generator
does not assess terrain, cover, observation, fire coverage or combat positions.
Building annotations do not assert physical access or occupancy permission.

| Component | Personnel |
| --- | ---: |
| RQ/SQ/TQ, four A–D platoons each, four groups of eight per platoon | 384 |
| Additional E platoon in each company, also four groups of eight | 96 |
| Company commander and deputy in each company | 6 |
| VQ commander and deputy | 2 |
| Battalion communications/admin platoon | 20 |
| S1=2, S2=2, S3/5=3, S4=2, S6=3 | 12 |
| Total | 520 |

The roster has 70 runtime units and 85 hierarchy markers. Platoon markers do
not add personnel beyond the specified 32 per platoon. These counts are the
exercise specification, not a claim about an official Swedish establishment.

Names come from TAKS's actual `identity_grammar.py`/`fal.py`, cross-checked
against the uploaded *FAL-A, 2020-04-22*, sections 1.1 and 1.2.3. Groups are
E–H. The first group's third person in company TQ is locally `EA3`, with
unique FALFAL identity `EATQ3` and visible simulation callsign `SIM-EATQ3`.
`RQ1/RQ2` are company command aliases; `AR1/AR2` refer to platoon AR.
Company command globally uses `RQVQ1/RQVQ2`. Battalion command uses `VQ1/VQ2`.
Communications and staff aliases are explicitly exercise-defined, not presented
as official FAL-A allocations.

## Cattle release

The fixed DevOps operations remain scoped to taklabs:

1. Back up the current node and retain its exercise export.
2. Stage a reviewed, pinned source commit.
3. `taks-release identities taklabs 520 confirm` configures the next boot.
4. Place bounded anchor JSON in the unit's `misc/simulation-anchors.json`.
5. `taks-release prepare-roster taklabs COMMIT confirm` builds the seed from
   that pinned source, preserving a copy of the previous seed.
6. Select the verified restore backup, build, and verify the actual archive.
   Verification checks that its pool can serve all seed slots.
7. Replace the exact old instance, wait for AWS absence, launch the fresh cow,
   then monitor `simulation/provisioning` and normal installer events.
8. Inspect the roster and activate cohorts through the Orchestration MCP.

A new roster has a new instance ID. The installer applies a selected new
instance even if an older exercise state was restored, while retaining a
rollback copy. Runtime geographic layouts, person state, exports and backup
reports are kept outside source repositories.

## Validation

Run the simulation, scale, orchestration and DevOps boundary tests. The optional
local probe `PYTHONPATH=takctl python tools/benchmark-simulation-tls.py` creates
520 distinct disposable ECDSA client keys/certificates and a local authenticated
relay. One Python process contains both the relay and the daemon. Its memory
and throughput measurements include both sides and do not establish capacity
of a production TAK Server or its RSA client certificates.

The observed local run connected all 520 identities, received all 605 objects,
and recorded no reconnects. It used about 373MiB peak for the combined process.
Its receive cache discarded more than 638,000 duplicate fan-out frames. Live
node results must be checked separately.
