# TAKS business MCP

Run from the orchestrator Python environment with the `orchestrator` directory on PYTHONPATH:

```sh
python -m taks_mcp.server
```

Default bind is 127.0.0.1:8766, Streamable HTTP path `/mcp`. Route this endpoint independently of the DevOps MCP listener. The service requires the existing loopback orchestrator API and a read-only service token file for authentication. Install the MCP Python dependency in the TAKS MCP environment.

This server owns units, node provisioning, lifecycle, and product-level health. Filesystem, process, AWS diagnostics and deployment belong exclusively to DevOps MCP. Do not expose this listener publicly without the authenticated ingress. Node-side MCP JSON-RPC forwarding is a separate API route and is not a complete Streamable HTTP implementation.

Deployment and live verification are required before enabling ChatGPT integration.
