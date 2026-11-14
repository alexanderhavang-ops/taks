# Idle-node evidence

The cost-saving task polls every three hours and requires **more than four hours**
of complete verified inactivity before automatic termination. An idle observation
and permission to terminate are separate results. The known-idle acceptance case
is takdiag with only Martine's periodic presence; that baseline must classify idle.

`service_read(node_id, service="activity", operation="status")` returns the same
evidence attached to each active node in inventory. It includes the exact EC2
instance, `observed_state`, last relevant activity, coverage start/end, blockers,
and `eligible_for_idle_shutdown`. No old quiet period is invented at installation.

The orchestrator keeps a small SQLite ledger of non-monitoring node tool use. The
node RPC bridge records accepted tool attempts before forwarding them. DevOps
wraps node-targeted native calls and keeps an audit heartbeat. Diagnostic reads,
activity polling, and the supported backup/restore/shutdown workflow do not count
as use. Tool names and timestamps are retained; arguments and results are not.

A shared asynchronous observer uses an existing protected unit client certificate
from a verified selected backup. It publishes no map contact. It compares received
CoT event counts with TAK Server input counters. Missing traffic, filtered group
visibility, counter resets, observer disconnects, and server/instance replacement
invalidate coverage. Server protocol announcements (`t-x-takp-v`) are not user
activity. Martine's local authenticated subscription pins the periodic bot UID;
its ordinary presence reports are excluded by UID, not by callsign. Other clients
count as use. Ambiguous bot messages conservatively extend the activity watermark.

Node input hooks additionally record timestamp-only watermarks before direct
XMPP/Martine requests and upon real voice-client/sound activity. Fresh XMPP and
voice receiver heartbeats and the installed agent hook version are required.
Disconnection or process restart changes the coverage epoch. No message bodies,
questions, transcripts, or audio are copied into this ledger. A fresh cattle
rollout starts the updated receiver processes; copying source into an old running
worker is insufficient. Native activity databases are separated by boot ID so
restoring an older WAL snapshot cannot manufacture coverage for a new node.

The assessment uses the earliest verified end across its sources. Missing, stale,
or incomplete source coverage blocks automatic shutdown. Observed idle is useful
for acceptance testing, but does not bypass the complete four-hour history rule.

For an eligible node: create and verify a complete state backup, select it for
restore, refresh evidence, and use the guarded DevOps shutdown with the exact
instance and backup. The existing identity/backup checks remain mandatory. The
shutdown request must carry `require_idle_evidence=true`; the API checks evidence
again immediately before termination. Manual, explicitly requested cattle
replacement remains a separate operation.

The orchestrator and TAKCTL services log to systemd's journal. Their product log
tools use bounded, redacted journal reads instead of assuming nonexistent files.
Those tails are diagnostics, not an activity ledger or proof of a quiet interval.
