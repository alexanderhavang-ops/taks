> [!IMPORTANT] Non-authoritative
> This file is an index and background only. **Authoritative contracts** live under `docs/`.
> If anything conflicts, the contract docs win.

# TAKS (monorepo)

TAKS is an opinionated framework for deploying and operating TAK nodes with an installer-owned runtime.

## Components
- `orchestrator/` – control plane (UI/backend)
- `orchestrator-installer/` – installs orchestrator host runtime (nginx + TLS + service)
- `tak-installer/` – installs tak-node runtime pieces (nginx, systemd units, takctl runtime sync)
- `takctl/` – takctl source (CLI + web backend + web UI)
- `llm-infra/` – installer-owned LLM subsystem wiring (optional)

## Documentation (start here)
- `docs/orchestrator.md`
- `docs/tak-node.md`
- `docs/certificates.md`
- `docs/takctl-ARCHITECTURE.md`
- `tak-installer/README.md`
- `llm-infra/README.md`

## Source → Runtime convergence (core rule)
- Source (git): `/opt/taks`
- Runtime (installer-owned): `/opt/tak/...`
- Convergence happens via: `./tak-installer/tak-installer apply`

## Deterministic node validation (DNS-independent)
Prefer SNI+Host forced to localhost:

- `curl --resolve "<FQDN>:443:127.0.0.1" "https://<FQDN>/takctl/api/health"`
- `curl --resolve "<FQDN>:443:127.0.0.1" "https://<FQDN>/takctl/api/meta"`

This avoids false negatives from stale DNS caches.
