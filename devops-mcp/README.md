# TAKS DevOps gateway

`app/` preserves the gateway source deployed at `/opt/taks-devops-mcp/app`.
Run `PYTHONPATH=devops-mcp python -m unittest discover -s devops-mcp/tests -v`
from the repository root. Existing configuration, filesystem policy, tunnels,
service identity and credentials remain external to this repository.

The lifecycle tools use the existing loopback orchestrator service-token bridge.
Backup list, verification and restore selection are scoped API routes. The
Business identity cannot use those routes, download archives, or terminate nodes.
Verification checks the archive's unit, manifest, paths and bucket checksums
without returning archive contents. Restore selection repeats verification.

Backup, verification, bundle preparation and launch return an operation ID.
Poll `taks_operation_status` until `done`, then inspect `result.ok`. The queue is
bounded and concurrent starts for the same target return the running operation.
Operation IDs are process-local: after a gateway restart or an uncertain timeout,
reconcile backup lists and AWS node inventory before retrying. Never infer failure
from a disconnected client or launch timeout. Running and pending AWS instances
block duplicate launches; stale registry rows alone do not.

Mutations require their confirmation flag. Shutdown additionally checks the
registered unit and expected instance ID, a selected restore backup, successful
integrity verification and all eight state buckets. The termination API checks
the expected instance ID again before calling AWS. Create a fresh backup and
complete bundle preparation before shutdown; keep one `t3.medium` TAK node.

Deployment: publish tested source in GitHub, deploy orchestrator API changes with
the pinned `deploy_orchestrator` tool, install changed gateway Python files using
checksum-guarded DevOps filesystem tools, and restart `taks-devops-mcp.service`
using its existing allowlisted restart operation. Retain prior file contents for
rollback. Verify gateway version, service status and the live MCP catalog. Refresh
the connected client's tool catalog if newly registered tools are not yet visible.
Do not enable arbitrary shell execution or broaden service credentials.
