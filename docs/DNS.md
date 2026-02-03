> [!IMPORTANT] Authoritative
> This document defines the **DNS & naming contract** for TAKS.
> Related authoritative contracts:
> - `docs/contracts/README.md`

# DNS & Naming Contract (Authoritative)

TAKS supports **multiple DNS scopes concurrently**.
This is intentional: it allows current/legacy deployments to keep working while orchestration moves to cloud-scoped zones.

## DNS scopes

### 1) Current / static (legacy-compatible)

These names are valid and must continue to be supported:

- **Orchestrator (master):** `master.tak-hv-sandbox.se`
- **TAK nodes:** `<battalion>.tak-hv-sandbox.se`

Characteristics:
- A/AAAA records are managed manually (or by whatever DNS provider owns the apex zone).
- Good for static hosts and “just keep it running” deployments.

### 2) Cloud-scoped (orchestration-ready)

Cloud-scoped zones isolate automation per cloud and keep multi-cloud possible:

- **AWS zone:** `aws.tak-hv-sandbox.se`
- **Orchestrator (master):** `master.aws.tak-hv-sandbox.se`
- **TAK nodes:** `<battalion>.aws.tak-hv-sandbox.se`

Future zones may exist, e.g.:
- `gcp.tak-hv-sandbox.se`
- `azure.tak-hv-sandbox.se`

Characteristics:
- Designed for dynamic provisioning (Elastic IP, Route53 automation, later LB/NLB).
- Orchestrator may manage records inside the cloud-scoped zone.

## DNS authority & delegation

### Apex zone provider (e.g. Loopia)

The apex zone remains where it is (authoritative for `tak-hv-sandbox.se`).
If using a cloud-scoped zone, the apex must delegate it via NS:

- Add NS records for:
  - `aws.tak-hv-sandbox.se` → Route53 nameservers

This allows migration without downtime:
- the apex stays put
- the cloud zone is delegated and automation-friendly

### Route53 hosted zone (AWS scope)

If you choose AWS cloud-scoped DNS, Route53 is authoritative for the delegated cloud zone:

- Hosted zone: `aws.tak-hv-sandbox.se`
- Records may be managed by the orchestrator:
  - `master.aws.tak-hv-sandbox.se` (A/AAAA)
  - `<battalion>.aws.tak-hv-sandbox.se` (A/AAAA)
  - optional: health/status records, etc.

## IP model

- **Orchestrator**: should use an Elastic IP when using cloud-scoped automation (stable).
- **Nodes**: may use Elastic IPs (stable) or other models later (LB/NLB, etc).

Static scope deployments may use any stable IP/DNS arrangement outside Route53.

## Certificates (Let’s Encrypt)

- nginx serves HTTP-01 challenge on **port 80**:
  - `/.well-known/acme-challenge/*`
- certbot requests/renews certificates
- nginx terminates TLS on **443** using issued certs

This requires:
- Public reachability to port 80 and 443
- Correct DNS A record pointing at the instance public IP (EIP recommended for cloud-scoped automation)
