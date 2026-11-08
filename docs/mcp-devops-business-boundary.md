# TAK node MCP responsibility boundary

The node exposes distinct `devops` and `taks` MCP domains. The
orchestrator's `taks_node_devops_probe` relays only explicitly allowlisted
read-only DevOps tools over the existing mTLS channel.

## DevOps ownership

- OS, memory, swap, filesystem capacity, host network sockets
- Nginx config, certificate expiry, service status/journal
- JVM process CPU, file descriptor counts, Java and TAK Server logs
- Installation and bootstrap steps, failed action diagnostics
- Reproducible provisioning and deployment (replace cattle, avoid host patches)

The bounded `netstat_listeners` command uses `ss` and only returns selected
TCP listening ports, addresses and visible PID numbers. `lsof_tak_java` only
summarizes descriptor types for identified TAK JVM PIDs, never raw file paths,
command lines, secret contents, or arbitrary processes.

## TAK Business ownership

- TAK clients, onboarding, certificates issued to users, connection diagnostics
- TAK application API operations and mission/business state
- Runtime quality, TAK service load, protocol readiness and performance
- Operational incident and degradation diagnosis

**Shared by design:** TAK Server installation failures, TAK Server readiness,
JVM initialization and related service logs. Business may retrieve *read-only*
startup/readiness summaries through its existing health tool, but is not granted
general host-admin operations, unrestricted shell execution or arbitrary files.

Later TAK Server API tools belong in the Business domain with independent
authorization. This document does not grant additional API permissions.

## Health semantics

- `systemctl active (exited)` is not proof that TAK JVMs initialized
- Check coreconfig, auth backend and 8089 / 8443 / 8446 separately
- LDAP mode does not require `UserAuthenticationFile.xml`
- Sustained JVM CPU can indicate initialization but does not prove readiness
- Installer actions must emit a terminal `Succeeded` or `Failed` event
