> ⚠️ Installer-owned subsystem
>
> Everything under `llm-infra/` is deployed, enabled, or disabled via
> `tak-installer apply`.
>
> Manual runtime changes are transient and may be overwritten.

# takctl – LLM subsystem

This directory defines the **LLM subsystem infrastructure** for `takctl`
(CLI + web backend + web UI).

This is **not a standalone product** and **not a chatbot**.

The LLM subsystem is a **planner and reasoning component** used by takctl
to generate structured, read-only insights over TAK Server data.

---

## What the LLM is (and is not)

### The LLM **is**
- A **planning engine**
- A **query proposer**
- A **summarizer** over structured results
- Stateless between requests (unless explicitly provided context)

### The LLM **is not**
- A database client
- A renderer
- A source of truth
- An executor
- A privileged component

The LLM is treated as **untrusted input**.

All effects are mediated by takctl.

---

## Core execution model

All LLM-backed functionality in takctl follows the same deterministic loop:

1. User intent (CLI command, web view, or API call)
2. System prompt + schema + context are constructed by takctl
3. LLM returns **strict JSON only**
4. JSON is validated against a protocol
5. If SQL is proposed:
   - SQL is validated (read-only, single statement)
   - SQL is executed by takctl
6. Results are returned to the LLM as JSON
7. LLM returns a final structured answer
8. takctl renders the result (CLI or Web)

At no point does the LLM:
- execute SQL
- see credentials
- control rendering
- modify system state

---

## Strict JSON protocol

All LLM responses **must** be valid JSON.

- No prose
- No markdown
- No code fences
- No side-channel text

Invalid responses are rejected and retried.

### Protocol versioning

LLM responses include a protocol version, e.g.:

```json
{
  "protocol": "taks.llm.agent.v1",
  "action": "query | final | clarify",
  "sql": "SELECT ...",
  "answer": "string",
  "title": "string | null",
  "render": null
}

The protocol is enforced by takctl, not the model.

SQL mediation (read-only)

The LLM may propose SQL queries as part of its reasoning.

Rules enforced by takctl:

Query must start with SELECT or WITH

Single statement only

No ;

No mutations

LIMIT is enforced by the system

The LLM never connects to the database directly.

Schema handling

The LLM is not expected to rediscover the schema on every request.

takctl provides:

table names

column names

basic relationships

bounded result windows

Schema snapshots may be cached and versioned.

Views are presets, not special cases

“Tactical Operations”, “Operational Security”, “System Health”, etc. are
not separate execution models.

They are:

predefined prompts

predefined schema subsets

predefined renderers

All views use the same agent loop.

CLI and Web parity

The same backend logic powers:

CLI (takctl llmchat, future view commands)

Web UI

Future ATAK integration

No LLM-only UI is introduced.

Rendering differs, execution does not.

Execution modes

takctl supports multiple LLM backends.

Local LLM (default)

Runs on-node

Offline / air-gapped

Lower capacity

Always available

Remote LLM (optional)

Explicitly configured

Higher capacity

Network-dependent

Optional augmentation

The system never assumes cloud connectivity.

Installer ownership

The installer is responsible for:

Deploying LLM binaries

Managing systemd units

Wiring nginx proxying

Enabling/disabling LLM usage

Ensuring isolation and permissions

Manual setup is unsupported and non-durable.

Non-goals

Explicitly out of scope:

Write access

User management

Certificate management

Autonomous actions

Persistent conversational memory

Those remain owned by TAK / Marti / takctl core services.

Status

Deterministic agent loop implemented

Strict JSON protocol enforced

SQL guard implemented

CLI development loop (llmchat) active

View presets in progress
