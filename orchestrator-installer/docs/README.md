# orchestrator-installer

Installs the **taks orchestrator** on an Ubuntu 22.04 EC2 instance.

## DNS

Supports both **static DNS** (manual A/AAAA records) and **cloud-scoped DNS** (e.g., Route53 for orchestration). Route53 is only needed for automated provisioning.

### Example FQDNs:
- `master.tak-hv-sandbox.se`
- `master.aws.tak-hv-sandbox.se`

