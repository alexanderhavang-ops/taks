# Prompt packs (LLM view intent)

Prompt packs define **operator/user intent** for each LLM-backed view.

They are **config** (not runtime state, not dynamic output).

## Principles

- View-specific
- Human-editable
- Versioned
- Small and bounded (avoid pasting large datasets into prompts)
- Data-agnostic: prompts describe *goals and priorities*, not SQL schemas

## Lifecycle

- Git provides **defaults** (this directory and `llm-infra/prompt-packs/`)
- Runtime can override defaults via:
  - UI edits saved as durable runtime state (DB or file), OR
  - orchestrator-provisioned overrides
- Each run references a `prompt_pack_id` (and optional revision hash)

## Suggested structure

Each view has a directory containing:

- `system.txt` : role + guardrails
- `user.txt`   : task statement + prioritization
- `schema.md`  : (optional) stable hints for what fields mean
- `layout.md`  : (optional) preferences for the RenderPlan (block types)

Example:
- `tactical-operations/system.txt`
- `tactical-operations/user.txt`

