# orchestrator-installer

Installs and converges the **taks orchestrator master** on Ubuntu 22.04.

This includes:
- nginx (ports 80/443)
- Let’s Encrypt (HTTP-01)
- orchestrator backend service
- runtime state directory

---

## DNS

Supports both:
- **Static DNS** (manual A/AAAA)
- **Cloud-scoped DNS** (e.g. Route53)

Route53 is **optional** and only required for automated provisioning.

### Example FQDNs
- `master.tak-hv-sandbox.se`
- `master.aws.tak-hv-sandbox.se`

