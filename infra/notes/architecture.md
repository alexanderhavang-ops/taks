# Architecture notes (TAK + LLM)

## Separation of concerns
- TAK host:
  - takserver + takctl (admin tooling + optional web UI)
  - may proxy to LLM via nginx but does not host models/binaries

- LLM host (48hvbat):
  - /opt/llm is a runtime-owned volume containing LLM binaries and models (not stored in git)
  - systemd unit llm-local runs llama.cpp server locally
  - health: /health (503 while loading model, then {"status":"ok"})

## Operational patterns
- Prefer immutable snapshots for /opt/llm contents:
  - bin/ (llama-server-avx2/avx512)
  - models/ (gguf)
  - systemd/ (unit)
  - install.sh (creates /usr/local/bin/llama-server symlink + installs unit)

- Cloud-init should:
  - set hostname
  - mount volume (by UUID or /dev/disk/by-id nvme-Amazon_Elastic_Block_Store_...)
  - run /opt/llm/install.sh
  - apt-get install libgomp1 (if needed)
  - enable --now llm-local
