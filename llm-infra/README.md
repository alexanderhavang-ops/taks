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

