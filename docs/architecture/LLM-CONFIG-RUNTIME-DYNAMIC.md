LLM subsystem: config vs runtime state vs dynamic execution

This document clarifies ownership, lifecycle, and mutability of data and behavior
in the takctl LLM subsystem.

The goal is to ensure:

CLI and Web share the same backend

Installer remains authoritative

User intent is editable without code changes

LLM behavior is bounded, auditable, and replaceable

Mental model

There are three layers, each with a different owner and lifetime:

Config – operator / user intent

Runtime state – durable system assets and data

Dynamic execution – per-request, ephemeral computation

Keeping these separate is critical to avoid brittleness and accidental coupling.

1) Config (operator & user intent)

Config answers: “What should the system do?”

Config is:

editable without code changes

expected to survive tak-installer apply

intentionally small and human-readable

safe to version

LLM-related config examples
Global LLM behavior

llm_enabled = true|false

llm_mode = local | remote | hybrid

llm_url = http://127.0.0.1:8090 (broker endpoint, not model runtime)

model selection policy (default / fallback)

execution budgets:

max planner iterations

max SQL rows per query

max total execution time

View-level config

which views are enabled (tactical, opsec, health)

data windows (e.g. last 6h / 24h)

sampling limits

redaction rules

whether planner traces are exposed

Prompt packs (user-editable)

Prompt packs describe intent, not data or layout.

They are:

view-specific

editable via UI

durable until changed

versioned

Example – Tactical Operations:

SYSTEM PROMPT
You are assisting a TAK server operator.
Your task is to summarize tactical information clearly and conservatively.
Prioritize correctness and alerts over speculation.

USER PROMPT
Summarize the tactical situation for friendly and known enemy units.
Highlight alerts and anomalies first.
Provide recommendations only when confidence is high.

For friendly units, consider:

location

current and recent missions

mission status

troop count

stridsvärde

stridsberedskap

wounded personnel

supply status

For enemy units:

summarize only what is supported by data

avoid speculation

Where config lives

Defaults: takctl.conf.example

Runtime config: /opt/tak/tools/takctl/takctl.conf

User-edited prompt packs:

small DB table or

versioned JSON/YAML files under an installer-preserved runtime path

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

Persistent caches or indexes that survive restarts

Rule of thumb:

If losing it during tak-installer apply would be unacceptable,
it is runtime state and must live in an installer-preserved path.

Runtime state may change over time, but it is still not dynamic execution.

3) Dynamic execution (per request, ephemeral)

Dynamic execution answers: “What is true right now, and what did we compute?”

Dynamic execution is:

request-scoped

reproducible

discardable

optionally cacheable (with TTL)

Examples

Tactical snapshot collected at request time

Database discovery results

Planner iterations and retries

LLM tool calls

Final view output

Streaming tokens or partial results

Nothing in this category should be relied on across restarts.

Snapshot → Plan → Render model

To keep CLI and Web identical at the backend level, views follow this flow:

1) Snapshot (deterministic input)

A bounded, structured snapshot of available data.

Properties:

versioned schema

explicit limits

provenance included

safe to log

Example shape:

schema_version: taks.snapshot.tactical.v1
timestamp: UTC
postgres:
  discovery: …
  latest_activity: …

2) Planner (LLM or heuristic)

Transforms snapshot + config into a RenderPlan.

Characteristics:

may iterate

may request additional data

bounded by config

fully auditable via tool traces

no reliance on hidden chain-of-thought

3) RenderPlan (stable output contract)

The only thing CLI and Web render.

Properties:

UI-agnostic

declarative

versioned

Example shape:

schema_version: taks.renderplan.v1
view: tactical-operations
meta:
  mode: llm
  model: local-small
datasets: …
blocks:
  - header
  - alerts
  - table


CLI maps blocks to Rich output.
Web maps blocks to React components.

Why this separation matters

Installer remains authoritative

LLMs can fail without breaking views

Heuristic fallback is always possible

UI can evolve independently of backend logic

Local and remote LLMs are interchangeable

No hidden reasoning is required or stored

One-sentence rules

Config: what we want the system to do

Runtime state: what is installed or saved

Dynamic execution: what we computed right now

If these boundaries stay clean, the system remains understandable, debuggable, and safe to evolve.
