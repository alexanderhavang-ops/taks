# MCP domain rollout (not yet deployed)

## Boundary
- TAKS Business MCP: orchestrator units, node launch/stop/start, provisioning dry-run and TAKS health. Owned by TAKS repository, `orchestrator/taks_mcp`. Loopback port 8766.
- DevOps MCP: filesystem, host processes, logs, AWS diagnostics and orchestrator deployment. Owned by devops-mcp repository. Loopback port 8765.
- Node endpoints: existing TAKCTL web service, `/api/orchestrator/mcp/taks` and `/api/orchestrator/mcp/devops`; tool catalogs in separate modules `takctl.web.mcp_domains.taks` and `devops`.
- One tunnel client and ingress can route to both loopback services, but maintain distinct externally registered MCP URLs, tool catalogs, access policies and credentials. Never expose loopback listeners directly.

## Before production
1. Review both draft PRs and run unit tests. Check the Python MCP dependency, installed package paths and systemd service executable path; the supplied service unit is a deployment template, not an executed installation.
2. Install the TAKS branch on the orchestrator and node via the existing approved release/bundle mechanism. Deploy the DevOps branch separately. Do not copy code directly to a running node as a substitute for deployment.
3. Create the TAKS MCP service account/credential with least-privilege access to the orchestrator API. Current initial implementation reuses the existing orchestrator loopback service token file; separate tokens and permission scopes are required before exposing two independent ChatGPT plugins.
4. Install and start `taks-business-mcp.service` using the correct virtualenv path. Keep DevOps MCP on 8765 and TAKS MCP on 8766. Configure the single ingress/tunnel to map independent MCP endpoints to each service. Authenticate at ingress and restrict DevOps access separately.
5. Verify both MCP `initialize`, `tools/list`, `tools/call` through their ChatGPT-facing URLs. Node bridge routes are currently a limited JSON-RPC subset, not full Streamable HTTP.
6. Repair the expired 49hvbat TLS certificate with verified trust chain. Do not disable TLS verification.
7. Run TAKS lifecycle stop/start against *only* authorized 49hvbat, then test both node domains through the orchestrator bridge and test DevOps and TAKS orchestrator domains independently.
8. Capture tool allowlist, authorization-denial and audit-log evidence before enabling broad chatbot access.

## Not yet implemented
- Full node configuration / TAK Server administration tool catalog.
- Production-grade independent service-token scopes (current loopback token is shared).
- End-to-end tunnel and ChatGPT plugin provisioning.
- Actual orchestrator code update/deployment MCP operation.
- Verified end-to-end node deployment and test.
