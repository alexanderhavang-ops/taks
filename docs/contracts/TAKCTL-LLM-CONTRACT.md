# TAKCTL LLM Contract (Authoritative)

This document defines the **authoritative contract** for the LLM subsystem
used by takctl (CLI and Web).

---

## Scope

The LLM subsystem includes:
- LLM HTTP client
- Prompt construction
- Agent loop
- SQL validation
- Structured JSON outputs

It does **not** include:
- rendering logic
- database credentials
- execution control
- system state mutation

---

## Trust model

The LLM is **untrusted**.

All LLM output must be:
- syntactically valid
- semantically validated
- explicitly approved by takctl

The system must remain correct even if the LLM is wrong.

---

## Protocol versioning

Current protocol:

taks.llm.agent.v1


The protocol version must be included in every LLM response.

---

## Required JSON structure

Every LLM response must be a single JSON object:

```json
{
  "protocol": "taks.llm.agent.v1",
  "action": "query | final | clarify",
  "sql": "string | null",
  "answer": "string | null",
  "title": "string | null",
  "render": "object | null"
}

Field rules

protocol
Must match the active protocol version exactly.

action
One of:

query – request SQL execution

final – final answer

clarify – request more user input

sql
Required only if action == "query".

answer
Required if action == "final" or clarify.

render
Optional hints only. No executable code.

Unknown fields are ignored.

SQL constraints

All SQL must:

start with SELECT or WITH

contain a single statement

not contain ;

be read-only

takctl enforces LIMITs regardless of LLM input.

Execution flow

takctl constructs system prompt + schema

LLM returns JSON

takctl validates structure

takctl validates SQL (if present)

takctl executes SQL

takctl returns results as JSON

LLM may iterate

takctl renders final output

Failure handling

Invalid JSON → retry or fail

Invalid SQL → rejected with reason

Timeout → abort agent loop

Max steps exceeded → fail with trace

All failures must be observable and logged.

Determinism guarantee

Given:

same user input

same schema snapshot

same DB state

takctl must produce the same result regardless of LLM phrasing.

Non-goals

The LLM contract does not allow:

database writes

file system access

system commands

cross-service orchestration

user management

Authority

This document overrides:

README descriptions

inline comments

experimental code

If code contradicts this contract, the code is wrong.

Failure handling

Invalid JSON → retry or fail

Invalid SQL → rejected with reason

Timeout → abort agent loop

Max steps exceeded → fail with trace

All failures must be observable and logged.

Determinism guarantee

Given:

same user input

same schema snapshot

same DB state

takctl must produce the same result regardless of LLM phrasing.

Non-goals

The LLM contract does not allow:

database writes

file system access

system commands

cross-service orchestration

user management

Authority

This document overrides:

README descriptions

inline comments

experimental code

If code contradicts this contract, the code is wrong.
