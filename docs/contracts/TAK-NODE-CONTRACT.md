# TAK Node Contract

This document defines the **contract** for a TAKS-managed node.

## Scope
A TAK node runs:
- TAK Server (Marti)
- takctl (CLI + web backend)
- nginx ingress managed by tak-installer

## Certificates
The node uses a **wildcard certificate** (e.g., `*.tak-hv-sandbox.se`).  
Certs are managed by the orchestrator, with offline nodes receiving encrypted certs.

