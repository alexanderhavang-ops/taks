# Prompt pack resolution and deployment

Prompt packs define **operator / user intent** for LLM-backed views.

This document defines:
- where prompt packs live
- how overrides work
- what `tak-installer apply` is responsible for

The model intentionally mirrors how **takctl web UI assets** are handled.

---

## Overview

Prompt packs exist in **3 places**, but only one is ever **active** at runtime.

- **User uploads** → editable source of truth
- **Deployed prompt packs** → built output the backend reads
- **Git defaults** → defaults only


The installer is responsible for convergence.

---

## Directories

### Runtime user uploads (override source of truth)

Editable, durable, preserved across redeploys.

Path:

```
/opt/tak/tools/takctl/user-uploads/prompt-packs/<view>/
```

Owned by:
- Web UI edits
- Shell edits
- Orchestrator provisioning (cloud-init or attached volumes)

This directory is considered **runtime state**.

---

### Deployed prompt packs (active runtime)


This is the **only location read by takctl** at runtime.

Path:

```
/opt/tak/tools/takctl/prompt-packs/<view>/
```

Owned by:
- `tak-installer apply`

This directory is **installer-owned output** and should not be edited manually.

---

### Git defaults (seed material)

Default prompt packs shipped in the source tree.

Path (source):

```
/opt/taks/llm-infra/prompt-packs/<view>/
```

These are used only when no runtime overrides exist.

---

## Convergence rule (installer behavior)

On `tak-installer apply`, for each LLM view:

1. If runtime overrides exist and contain required files:
   - copy from:
     ```
     /opt/tak/tools/takctl/user-uploads/prompt-packs/<view>/
     ```
   - into:
     ```
     /opt/tak/tools/takctl/prompt-packs/<view>/
     ```

2. Else:
   - copy defaults from:
     ```
     /opt/taks/llm-infra/prompt-packs/<view>/
     ```
   - into:
     ```
     /opt/tak/tools/takctl/prompt-packs/<view>/
     ```

There are ***no additional fallbacks**.

---

## Required files

A prompt pack must contain:
- `system.txt`
- `user.txt`

Optional files:
- `schema.md`
- `layout.md`

If required files are missing in **both** runtime overrides and defaults:
- fail explicitly
- surface a clear error in both CLI and Web UI- do not invent or inline prompts in code

---

## Rationale

This model ensures:

- Orchestrator can pre-seed prompt packs for new nodes
- Local edits persist (Web UI or shell)
- Defaults remain versioned and reviewable
- takctl reads from a single, stable runtime path
- Installer remains authoritative
- LLC behavior is predictable and auditable

---

## Relationship to other concepts

- Prompt packs are **config**, not runtime assets
- Uploaded logos and UI assets follow the same lifecycle model
- Prompt packs are resolved **before** any LLM execution
- Dynamic execution never mutates prompt packs
