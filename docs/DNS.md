# DNS & Naming Contract (Frozen)

This project supports the idea of multiple clouds in the future. To avoid mixing concerns, we use a cloud-scoped delegated DNS zone per cloud.

## Canonical DNS model

- **Cloud zone (AWS):** `aws.tak-hv-sandbox.se`
- **Orchestrator (master):** `master.aws.tak-hv-sandbox.se`
- **TAK nodes:** `<battalion>.aws.tak-hv-sandbox.se`
  - example: `48hvbat.aws.tak-hv-sandbox.se`

This avoids ambiguity and keeps future multi-cloud possible:
- `gcp.tak-hv-sandbox.se` (future)
- `azure.tak-hv-sandbox.se` (future)

## DNS authority & delegation

### Route53 hosted zone
Route53 is authoritative for the delegated cloud zone:

- Hosted zone: `aws.tak-hv-sandbox.se`
- Records managed by the orchestrator:
  - `master.aws.tak-hv-sandbox.se` (A/AAAA)
  - `<battalion>.aws.tak-hv-sandbox.se` (A/AAAA)
  - optional: health/status, etc.

### Registrar / existing DNS provider (e.g. Loopia)
Your registrar (or existing DNS provider) remains authoritative for the apex zone (`tak-hv-sandbox.se`) but **delegates** the cloud sub-zone:

- Add NS records for:
  - `aws.tak-hv-sandbox.se` → Route53 nameservers

This allows migration without downtime: the apex stays where it is, the cloud zone is delegated.

## IP model

- **Orchestrator**: should use an Elastic IP (stable)
- **Nodes**: can use Elastic IPs (stable) or other models (LB/NLB later). For now assume EIP for simplicity.

## Certificates (Let’s Encrypt)

- Nginx serves HTTP-01 challenge on **port 80**:
  - `/.well-known/acme-challenge/*`
- Certbot requests/renews certificates
- Nginx terminates TLS on **443** using the issued certs

This requires:
- Public reachability to port 80 and 443
- Correct DNS A record pointing at the instance public IP (EIP recommended)
