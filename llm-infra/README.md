> ⚠️ Installer-owned subsystem
>
> Everything under `llm-infra/` is deployed, enabled, or disabled via `tak-installer apply`.
> Manual changes are transient and may be overwritten.

# takctl – LLM subsystem

This directory defines the **LLM subsystem of takctl**.

It is not a standalone product and not an experiment.
It is part of the takctl architecture and follows the same model:

- Backend services
- CLI frontend
- Web frontend
- Installer-managed deployment
- Optional ATAK integration

The LLM subsystem provides AI-assisted operational views over TAK Server data.


## Position in the overall system

takctl consists of:
- A Python backend (services + domain logic)
- A CLI frontend
- A Web frontend (FastAPI + UI)
- Optional ATAK-facing APIs

The LLM subsystem is **one capability of takctl**, not a separate tool.

Deployment and lifecycle are owned by:
- `tak-installer apply`


## LLM execution models

takctl supports **two LLM execution modes**, both optional and explicitly configured.

### 1) Local on-node LLM (default)

Every tak-node may run a **local LLM**:

- Runs on the same machine as the TAK Server
- Uses llama.cpp (or equivalent)
- No external connectivity required
- Works fully offline / air-gapped
- Lower capacity, but always available

This model guarantees that:
- takctl LLM features still work in offline environments
- No cloud dependency is assumed


### 2) Remote LLM (optional)

Optionally, takctl may use a **remote, more powerful LLM**:

- Runs on a separate host (e.g. EC2 with GPU)
- Reachable from the tak-node over the network
- Explicitly enabled by configuration
- Can replace or augment the local LLM

Typical use cases:
- Heavier summarization
- Larger context windows
- Interactive admin chat

The system does **not** assume EC2.
The remote LLM may be:
- Cloud-based
- On-prem
- Another offline machine on a restricted network


## LLM-backed views in takctl

The LLM is not a general chatbot by default.
It is used to power **specific operational views**.

Initial planned views:

### 1) Tactical Operations

Purpose:
- Analyze tactical data produced by TAK usage

Typical inputs:
- Missions
- Chats
- CoT messages
- Unit positions
- Activity timelines
- Selected logs

Outputs:
- Situation summaries
- Detected patterns or anomalies
- Operational recommendations

This view is read-only and advisory.


### 2) Operational Security

Purpose:
- Summarize the **security posture** of the TAK Server node

Typical inputs:
- Certificates and expiry
- CRL status
- Connected clients
- Users and groups
- Authentication events
- Suspicious or anomalous log entries

Outputs:
- Security summary
- Warnings and risk indicators
- Suggested remediation actions

This view complements, but does not replace, explicit security controls.


### 3) System Health

Purpose:
- Provide a high-level health overview of the node

Typical inputs:
- CPU, memory, disk
- Service restarts
- OOM events
- Error logs
- Installer state
- Recent failures

Outputs:
- Health summary
- Degradation indicators
- Clear “what to look at next” guidance


### 4) (Optional) Admin Chat

Optional interactive mode:

- Natural-language interface for administrators
- Queries routed through takctl services
- Typically enabled only when a remote LLM is configured

Examples:
- “Why is this node marked yellow?”
- “Which clients failed auth today?”
- “What changed since yesterday?”

This is explicitly **not required** for core operation.


## Frontends

All LLM-backed views are exposed through the same interfaces as the rest of takctl:

- **CLI**
- **Web UI**
- **Future ATAK plugin**

No LLM-only UI is introduced.


## Installer ownership

The LLM subsystem is installer-managed.

The installer is responsible for:
- Deploying local LLM binaries if enabled
- Installing systemd units
- Wiring nginx proxying if needed
- Ensuring correct permissions and isolation
- Enabling or disabling remote LLM usage

Manual setup is unsupported and non-durable.


## Offline-first design

takctl LLM features are designed with the same constraints as TAK itself:

- Offline operation is first-class
- No cloud dependency is assumed
- All remote functionality is opt-in

If a node is offline:
- Local LLM continues to work
- Remote LLM is simply unavailable
- No feature silently degrades without being reported
## Deterministic node validation (2026-02-02)

When diagnosing node reachability, prefer tests that do not rely on external DNS state.

For nginx vhosts, you can force SNI+Host to the node FQDN while connecting to localhost using:

- `curl --resolve "<FQDN>:443:127.0.0.1" https://<FQDN>/takctl/api/health`
- `curl --resolve "<FQDN>:8446:127.0.0.1" https://<FQDN>:8446/Marti/api/version`

This is the same technique used by tak-installer smoketests and is resilient to stale DNS caches.

# LLM subsystem: config vs runtime state vs dynamic execution

This document clarifies **ownership, lifecycle, and mutability** of data and behavior
in the takctl LLM subsystem.

The goal is to ensure:
- CLI and Web share the same backend
- Installer remains authoritative
- User intent is editable without code changes
- LLM behavior is bounded, auditable, and replaceable

---

## Mental model

There are **three layers**, each with a different owner and lifetime:

1. **Config** – operator / user intent  
2. **Runtime state** – durable system assets and data  
3. **Dynamic execution** – per-request, ephemeral computation  

Keeping these separate is critical to avoid brittleness and accidental coupling.

---

## 1) Config (operator & user intent)

**Config answers:** *“What should the system do?”*

Config is:
- editable without code changes
- expected to survive `tak-installer apply`
- intentionally small and human-readable
- safe to version

### LLM-related config examples

#### Global LLM behavior
- `llm_enabled = true|false`
- `llm_mode = local | remote | hybrid`
- `llm_url = http://127.0.0.1:8090` (broker endpoint, not model runtime)
- model selection policy (default / fallback)
- timeouts and budgets:
  - max planner iterations
  - max SQL rows per query
  - max total execution time

#### View-level config
- which views are enabled (`tactical`, `opsec`, `health`)
- data windows (e.g. last 6h / 24h)
- sampling limits
- redaction rules
- whether traces are exposed to the user

#### Prompt packs (user-editable)
Prompt packs describe **intent**, not data or layout.

They are:
- view-specific
- editable via UI
- durable until changed
- versioned

Example (Tactical Operations):

```text
SYSTEM PROMPT:
You are assisting a TAK server operator.
Your task is to summarize tactical information clearly and conservatively.
Prioritize correctness and alerts over speculation.

USER PROMPT:
Summarize the tactical situation for friendly and known enemy units.
Highlight alerts and anomalies first.
Provide recommendations only when confidence is high.

For friendly units, consider:
- location
- current and recent missions
- mission status
- troop count
- stridsvärde
- stridsberedskap
- wounded personnel
- supply status

For enemy units, summarize only what is supported by data.
Avoid speculation.
Where config lives
Defaults: takctl.conf.example

Runtime config: /opt/tak/tools/takctl/takctl.conf

User-edited prompt packs:

small DB table or

versioned JSON/YAML files under installer-preserved runtime path

2) Runtime state (durable system state)
Runtime state answers: “What do we have installed or saved?”

Runtime state:

is not source code

is not user intent

should not be wiped by redeploys

changes only when an operator or orchestrator acts

Examples in the LLM subsystem
Local model payloads
/opt/llm/models/*.gguf

Uploaded UI assets (logos, slogans)

Installed certificates and CRLs

Rendered nginx and systemd units

TAK database contents

Any persistent caches or indexes that survive restarts

Rule of thumb:

If losing it during tak-installer apply would be unacceptable,
it is runtime state and must live in an installer-preserved path.

Runtime state may change over time, but it is still not “dynamic execution”.

3) Dynamic execution (per request, ephemeral)
Dynamic execution answers: “What is true right now, and what did we compute?”

This layer is:

request-scoped

reproducible

discardable

optionally cacheable (with TTL)

Examples
Tactical snapshot collected now

Database discovery results

Planner iterations and retries

LLM tool calls

Final view output

Streaming tokens / partial results

Nothing here should be relied on across restarts.

Snapshot → Plan → Render model
To keep CLI and Web identical at the backend level, views follow this flow:

1) Snapshot (deterministic input)
A bounded, structured snapshot of available data.

versioned schema

explicit limits

provenance included

safe to log

Example:

json
Copy code
{
  "schema_version": "taks.snapshot.tactical.v1",
  "ts_utc": "...",
  "postgres": {
    "discovery": {...},
    "latest_activity": [...]
  }
}
2) Planner (LLM or heuristic)
Transforms snapshot + config into a RenderPlan.

may iterate

may request more data

bounded by config

fully auditable via tool traces

no reliance on hidden chain-of-thought

3) RenderPlan (stable output contract)
The only thing CLI and Web render.

UI-agnostic

declarative

versioned

Example:

json
Copy code
{
  "schema_version": "taks.renderplan.v1",
  "view": "tactical-operations",
  "meta": { "mode": "llm", "model": "local-small" },
  "datasets": { ... },
  "blocks": [
    { "type": "header", "title": "Tactical Operations" },
    { "type": "alerts", "dataset": "alerts" },
    { "type": "table", "dataset": "units" }
  ]
}
CLI maps blocks → Rich.
Web maps blocks → React components.

Why this separation matters
Installer remains authoritative

LLMs can fail without breaking views

Heuristic fallback is always possible

UI can evolve independently of backend logic

Remote and local LLMs are interchangeable

No hidden reasoning is required or stored

One-sentence rules
Config: what we want the system to do

Runtime state: what is installed or saved

Dynamic execution: what we computed right now

If these boundaries stay clean, the system remains understandable,
debuggable, and safe to evolve.
