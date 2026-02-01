# Chatpack

`tools/chatpack` generates a single Markdown file that captures the current repo state
(architecture notes + key code/config) so a new ChatGPT chat can pick up instantly.

Usage:
  tools/chatpack > chatpack/latest.md

Tips:
- Keep secrets out of the repo; chatpack does light redaction but is not a vault.
- Prefer stable paths; if you move files, update tools/chatpack.
