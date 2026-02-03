> [!IMPORTANT] Non-authoritative
> This document is **background**. For authoritative contracts, start at:
> - `docs/contracts/README.md`

# Certificate Architecture

TAKS manages TLS certificates for TAK nodes with a focus on:
- Security
- Offline survivability
- Operational clarity

## Default model: Wildcard certificate

The default and recommended model is a single wildcard certificate:

*.tak-hv-sandbox.se

This certificate is used for:
- Enrollment endpoints
- WebTAK
- takctl UI
- Any HTTPS ingress on battalion nodes

### Why wildcard?

- Simplifies provisioning of new battalions
- Avoids per-node DNS & LE issuance overhead
- Works cleanly with offline distribution
- Matches real-world battalion lifecycle (nodes come and go)

Per-node certificates **may be added later** but are not the default.

---

## Certificate authority

Certificates are issued using **Let’s Encrypt**.

Two issuance paths exist:

### 1. Orchestrator-issued (default)
- Orchestrator performs **DNS-01**
- Wildcard cert is obtained centrally
- Cert artifacts are distributed to nodes

### 2. Node-issued (online nodes only)
- Node performs **HTTP-01**
- Requires:
  - Public reachability
  - Correct DNS
  - Explicit config flag

This is optional and disabled by default.

---

## Online vs Offline nodes

### Online nodes
- Can:
  - Receive certs pushed by orchestrator
  - Optionally self-renew via HTTP-01
  - Report installed cert serial/fingerprint

### Offline / air-gapped nodes
- Cannot reach Let’s Encrypt
- Cannot perform HTTP-01
- Receive certs as **encrypted artifacts**
- Installation is tracked explicitly in the orchestrator

---

## Certificate lifecycle states

Each node has an explicit cert deployment state:

- `ISSUED` – cert created by orchestrator
- `AVAILABLE_FOR_DOWNLOAD` – artifact prepared
- `DOWNLOADED` – operator downloaded artifact
- `INSTALLED_UNVERIFIED` – operator marked installed
- `INSTALLED_VERIFIED` – node or operator provided proof
- `SUPERSEDED` – replaced by newer cert
- `REVOKED` – explicitly invalidated

No state is inferred silently.

---

## Verification models

### Automatic (online)
- Node reports installed cert serial/fingerprint
- Orchestrator verifies match → `INSTALLED_VERIFIED`

### Manual (offline)
One of:
- Upload cert proof (serial / fingerprint)
- Upload signed install receipt (future)

---

## Renewal strategy

- Certificates are renewed ~30 days before expiry
- Renewal produces a **new cert version**
- Old cert remains valid until expiry
- Nodes may temporarily lag without breaking enrollment

The orchestrator UI clearly shows:
- Which nodes are up-to-date
- Which are pending install
- Which are at risk of expiry

---

## Security notes

- Private keys are never re-generated on nodes
- Artifacts are encrypted per node or per operation
- Installer fully owns cert placement and permissions

