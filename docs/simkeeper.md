# TAKS SimKeeper

SimKeeper is the state keeper behind the existing `taks-simulation.service`.
ChatGPT decides what happens through MCP; SimKeeper executes explicit instructions,
maintains connections, and saves state. It contains no model, planner, or inference loop.
ATAK is an observer/client; TAK Server distributes CoT and GeoChat. Openfire carries
XMPP; Mumble carries voice. All simulated identities share one asyncio process.

## Background routes

Use `simulation_control` operations with `request_id`, `expected_revision`,
`unit_id`, and `entity_id`:

* `background_put`: `waypoints` (1–64 entries), `repeat` (default false),
  `delay_s` (default zero). Each entry has `position: {lat,lon}`, `travel_s`
  (10–86400), and `wait_s` (0–86400). Speed and geometry use the same validation
  as explicit movement. A repeating route must end at its starting position.
* `background_pause`, `background_resume`, `background_remove`.

Policies may be installed while a unit is inactive. They run only while active,
fit, and unpaused. Route elapsed time and phase survive a daemon restart. Downtime
is frozen, not replayed. Paths interpolate between supplied coordinates; there is
no automatic road snapping or obstacle avoidance. Obtain road/pedestrian geometry
through the separate map tools before supplying a route.

An individual or unit movement order, stop, deactivation, or injury suspends the
relevant policies. After a foreground relocation, install a new route from the
current position; resuming an old route is rejected if it would snap the actor back.
Completed one-shot policies require replacement. Timing follows the simulation
clock, with positions normally published on the configured ten-second CoT tick.
No ambient dialogue or stories are generated.

## Communications

Activation opens CoT, XMPP, and Mumble sessions for each provisioned actor;
deactivation closes them. XMPP uses verified direct TLS, dedicated LDAP account
credentials in protected files, and rooms derived by TAKS onboarding. Mumble uses
verified TLS and a separate per-actor VX-style certificate whose CN matches the
live CoT UID. The existing TAKS authenticator checks UID/callsign presence on TAK.
No shared Mumble service credential or authentication bypass is introduced.

`xmpp_chat` takes `target` (a provisioned actor's bare JID or a selected room JID)
and `message`. Incoming XMPP chat enters the recipient's durable inbox; joining
requests no history, and delayed history is ignored. Incoming messages never
execute commands automatically. Actor knowledge remains separate from world truth.

`mumble_channel` takes a provisioned channel name. Channel lookup uses the actual
server channel tree, never a guessed numeric ID. The acknowledged current channel
is exposed separately from the requested channel. One voice client occupies one
channel at a time; this version does not subscribe to multiple channels.

`mumble_ptt` takes `clip_id`, naming a prepared file in the configured audio directory.
Clips must be mono PCM16 WAV at 48 kHz, 20 ms–10 seconds. libopus encodes the clip on
demand using the shared worker; paced Opus packets use Mumble's TCP tunnel. This
avoids per-soldier codec processes and UDP encryption state. Calls return `queued`;
transport status reports transmission progress. Prepared audio is external to the
repository. There is no built-in TTS, voice transcription, or automatic spoken reply.
Voice reception is drained and counted; Mumble text enters the recipient inbox.

The normal optimistic-revision/idempotency contract applies to network actions.
Their intent is saved before sending; uncertain sends are not automatically replayed
after a crash. TLS writes/queued stanzas are not acknowledgments of human receipt.
A disconnect or deactivation can interrupt a clip.

Status includes per-actor transport connection, selected/joined XMPP rooms, actual
voice channel, retry/error counters, and PTT state. No passwords or keys are exported.
Disabled transport settings preserve older deployments' CoT-only behavior. Large
exercises require new profiling: three TLS sockets per person increase memory;
this release does not claim a sixteen-kilobyte-per-person footprint.
