> [!IMPORTANT] Non-authoritative
> This document is **background**. For authoritative contracts, start at:
> - `docs/contracts/README.md`

# LLM (llama.cpp) appliance notes

This folder contains:
- systemd unit template for `llm-local`
- nginx proxy snippet (optional) to expose LLM behind the TAK host
- cloud-init example for 48hvbat-like instances
- chatpack script to generate context for a fresh ChatGPT chat

## Roles

- LLM host (e.g. 48hvbat):
  - mounts /opt/llm (EBS snapshot)
  - `llm-local.service` runs `/usr/local/bin/llama-server ... -m /opt/llm/models/...`
  - exposes health at: http://127.0.0.1:8090/health

- TAK host:
  - may proxy to LLM host via nginx (optional)
  - takctl web backend unrelated, but chatpack can capture its state

## Health semantics
- LLM returns 503 while model is loading; later returns {"status":"ok"} at /health.
