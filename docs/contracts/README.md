# Contracts (Authoritative)

These documents define the stable, non-negotiable contracts for TAKS components.
If anything conflicts with other docs, **these contracts win**.

## Read order (recommended)

1. `TAK-NODE-CONTRACT.md` — what a node *is* (ports, TLS, ownership, green/yellow/red)
2. `TAK-INSTALLER-CONTRACT.md` — how a node is converged (plan/actions/dry-run/idempotence)
3. `TAKCTL-CONTRACT.md` — takctl runtime + web/API + privilege boundaries
4. `ORCHESTRATOR-CONTRACT.md` — control plane responsibilities + state model
5. `ORCHESTRATOR-INSTALLER-CONTRACT.md` — how the orchestrator host is converged (nginx+LE+service)

## Index

- `TAK-NODE-CONTRACT.md`
- `TAK-INSTALLER-CONTRACT.md`
- `TAKCTL-CONTRACT.md`
- `ORCHESTRATOR-CONTRACT.md`
- `ORCHESTRATOR-INSTALLER-CONTRACT.md`

## Related authoritative docs

- `../DNS.md` — DNS & naming contract (authoritative for naming)

## Terminology

See: `GLOSSARY.md`
