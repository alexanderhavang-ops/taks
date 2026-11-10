# Standalone watch voice onboarding

This TAKS change pairs with WearTAK Voice **0.3 audio onboarding alpha** in
[the watch repository](https://github.com/alexanderhavang-ops/weartak-voice).
It adds an audio button to the existing interactive soldier onboarding card, in Swedish
and English. It does not change WearTAK itself, ATAK Companion, or existing Vx packages.

## Operator flow

Open **Listen for setup** in the watch app. On the phone's existing TAKS card, tap
**Play audio code** and hold the speaker near the watch. Confirm the TAKS hostname on the
watch, download and accept the voice profile, then connect. The first assigned channel is
joined automatically. No keyboard input on the watch is required.

The sound carries a short-lived voice enrollment link, not the long-lived soldier card
URL, TAK password, Mumble password or private key. The watch obtains its credentials itself
over public, validated HTTPS. A future WearTAK integration can reuse the WTK1 link transport
with an explicitly defined WearTAK profile; that receiver is not part of this change.

## Backend contract and boundaries

- POST `/api/onboarding/cards/{card-token}/watch-voice/ticket`: validate the existing card
  and user, then mint a random 256-bit, three-minute, single-use ticket. Return
  `https://HOST/api/onboarding/cards/watch-voice#TICKET` and `expiresIn`.
- POST `/api/onboarding/cards/watch-voice/redeem`, body `{"ticket":"..."}`: atomically consume
  the ticket, revalidate the parent card and user, resolve selected channels against the
  actual Murmur database, and return voice profile schema 1. Maximum request body 512 bytes.
- Response: `schema`, `host`, `port`, `username`, `password`, `displayName`, `missionName`,
  `credentialExpiresAt` (Unix seconds), `channels: [{id, name}]`.
- POST `/api/onboarding/cards/{card-token}/watch-voice/revoke`: revoke all watch credentials
  and pending tickets for that account. Available under **Reset watch access** on the card.
- Responses are `no-store`. The bearer ticket is placed in the link fragment and redeem
  request body so ordinary request-URL logs do not record it. Do not enable body logging.
- The browser generates the acoustic waveform locally with Web Audio; no sound file or
  operator credential is uploaded or written. The watch processes received PCM in memory.
- Audio still carries a redeemable bearer capability. Use a private nearby setup, just as
  with credential QR codes. A recorder could race to redeem it; there is no claim of
  acoustic confidentiality or cryptographic binding to a particular watch microphone.
- The existing card token remains the authority. Ticket expiry and concurrent replay are
  enforced with SQLite transactions, independent of the number of web workers.

The credential database is `/opt/tak/takctl-state/onboarding/watch-voice/credentials.sqlite`
(mode 0600, newly created directory 0700). It stores hashes of tickets and watch passwords,
plus a temporary parent-card reference. Expired tickets are purged on issuance.
Keep it out of source control, public bundles and diagnostics.

## Mumble authentication

The current TAKS Vx path authenticates device/callsign claims against recent TAK presence;
it cannot bootstrap an independently operating watch by itself. This change therefore
adds an explicit `TW.<random-id>` namespace ahead of the existing Vx/service branches.
The generated authenticator imports `takctl.onboarding.watch_voice` and verifies that
watch's random 256-bit password against its stored hash. Failures never fall back to a
shared password or to Vx's presence check.

The server returns the account name plus `(watch)` as its display name and gives it a
separate user ID. IDs are allocated in a reserved 2,140,000,000–2,146,999,999 range, separate
from existing Vx and service ranges. Existing channel ACL policy is retained: the downloaded
selection is a convenience and is not a new channel authorization boundary.

Watch credentials expire after 30 days; at most ten unexpired logins per account are
retained. Repeat onboarding to renew. Reset watch access or delete the account to revoke
them. Revocation/expiry applies at authentication and does not disconnect existing sessions.
No TAK certificate/private key or shared service password is sent to the watch. Reusing TAK
mTLS and hardening existing Vx certificate authentication remain separate tasks.

## Rollout

Deploy the matching TAKCTL modules and generated authenticator together through the normal
node update mechanism; updating only the web page will produce credentials an old adapter
cannot accept. Runtime files affected:

- `takctl/api/onboarding_packages.py`, `takctl/api/onboarding_identity.py`
- `takctl/onboarding/watch_voice.py`, `takctl/onboarding/watch_voice_profile.py`
- `takctl/onboarding/soldier_card/page.py`, `watch_audio.py`, `watch_audio.js`
- canonical `takctl/bin/taks-mumble-voice-pin-auth.py`, installed root-owned by the Mumble action.

The generated adapter must find the installed `takctl` package at `/opt/tak/tools/takctl`.
Apply the installer-managed authenticator update, restart its service
`taks-mumble-voice-pin-auth.service`, and restart `takctl-web.service` after the modules are
installed. Preserve current files for rollback. Do not rerun the entire Mumble installation
merely to refresh the script, because that action also manages channel/database state.

Verify health, the card button, ticket issuance/expiry/replay, a complete watch login, assigned
channel joining, microphone/PTT release, and a regression Vx login. For rollback restore the
previous web modules and authenticator and restart the same services; existing Vx behavior
remains independent of the watch credential DB. Deleting the DB revokes all watch logins.

## Repeatable checks

```bash
PYTHONPATH=takctl python3 -m pytest takctl/tests -q
python3 tools/check_watch_voice_mumble.py --server /usr/bin/mumble-server
```

The second command requires distribution Ice Python bindings and Slice includes. It starts a
loopback-only server, runs the *actual generated* Ice authenticator, checks valid login and
wrong/malformed/revoked/expired credential rejection, then stops both processes and removes
all synthetic credentials. It never connects to a production node.

The watch repo's `scripts/check_browser_audio.py --taks-source /path/to/taks` feeds the actual
browser waveform into its Java decoder. The transport specification is maintained in the
watch repo's `docs/AUDIO_ONBOARDING.md`. Hardware tests on SM-L715F remain outstanding.

Verified locally: 35 TAKCTL tests passed; the actual generated Ice authenticator on Murmur
1.5.735 passed valid-login and wrong/malformed/expired/revoked rejection checks. The watch
client suite passed all 53 tests with browser and real-Mumble fixtures. Signed release
build and Android lint passed. Physical acoustic/button tests are pending.

The voice block also offers a fresh ticket QR and the existing VX channel-package download. The admin user view links to the same soldier-card voice section. QR and audio each issue a new, three-minute ticket. Watch credential SQLite state is backed up through SQLite snapshotting with TAKCTL state.
