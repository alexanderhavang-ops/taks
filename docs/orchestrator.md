> [!IMPORTANT] Non-authoritative
> This document is **background**. For authoritative contracts, start at:
> - `docs/contracts/README.md`

# Orchestrator Architecture

The orchestrator is the control plane for TAKS.

It does **not** run TAK itself.

---

## Responsibilities

- DNS-01 certificate issuance (Let’s Encrypt)
- Certificate inventory & versioning
- Node state tracking (reachability, cert state)
- Secure artifact distribution
- Operator UI for offline workflows

---

## Node state model

Each battalion node tracks:

### Reachability
- Reachable (green)
- Unknown (yellow)
- Offline (gray/red)

### Certificate state
- Up-to-date
- Pending deployment
- Expiring / expired
- Unknown installed state

These dimensions are independent.

---

## Offline workflow UX

For offline nodes the UI allows:

- Download encrypted cert bundle
- Mark as installed
- Upload install proof (optional)
- Track pending / verified state explicitly

No assumptions are made.

---

## Push vs pull

If a node is reachable:
- Orchestrator may push certs automatically

If unreachable:
- Operator-driven workflow applies

Both models converge on the same state machine.

---

## Future extensions

- Multi-domain support
- Per-battalion policy
- Certificate revocation workflows
- Automated compliance reports

