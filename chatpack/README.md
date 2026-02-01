# Chatpack

This repo keeps a ChatGPT-ready context pack up to date.

## Generate snapshot
- Writes `chatpack/latest.md` by default:

  tools/chatpack-orchestrator generate
  # or:
  tools/chatpack generate

## Print to stdout (for copy/paste)
  tools/chatpack-orchestrator print --include-tree

## Append journal entries (so future chats can extend context)
  tools/chatpack-orchestrator append --title "..." --text "..."
  tools/chatpack-orchestrator append --title "..." --file orchestrator-installer/scripts/orch-install

Notes:
- Redaction is best-effort and not a vault. Don’t store secrets in-repo.
