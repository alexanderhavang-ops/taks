# Orchestrator Installer

- `cloud-init/orchestrator.yaml` is the user-data bootstrap.
- `scripts/orch-install` is the idempotent installer entrypoint (plan/apply/verify).
- Cloud-init should do only: write env + drop orch-install + run `orch-install apply`.
