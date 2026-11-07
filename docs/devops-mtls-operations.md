# Node DevOps MCP mTLS operational policy

## Trust boundary

The orchestrator owns a dedicated private DevOps CA, separate from TAK Server's CA and public Let's Encrypt TLS. Its CA key is never sent to a node. The orchestrator presents a CA-signed client identity to each node; each node presents a distinct CA-signed server identity with SAN `devops.<node-fqdn>`. Nginx requires a valid client certificate for the DevOps virtual host. The TAKS Business domain continues to use the public HTTPS host and the orchestrator-node application secret.

## Issuance and custody

- Store the CA certificate, signing key, and orchestrator client identity in the orchestrator persistent `state/devops-pki/` directory, on persistent encrypted storage, with restricted root/service-account access. Back up the CA key encrypted, with access logged and limited to designated operators. Do not put it in Git, image snapshots, logs, or node bundles.
- Initialize the CA once. Never silently replace a missing, invalid, or expiring CA when another CA already exists. A missing key with an existing certificate is a hard failure.
- At each complete bundle build, generate a new node server key and a 90-day server certificate with DNS SAN `devops.<node-fqdn>`. Include only the node key, server certificate, and public CA certificate in the bundle.
- Generate an orchestrator client certificate signed by the same CA; keep its private key on the orchestrator. Rotate this client certificate before expiry. Validate chain, key correspondence, validity and SAN before publishing a bundle.
- Bundle archives contain a private node key and must be access-controlled and retained only as long as necessary. Serve bundles over HTTPS using the per-launch `X-TAKS-Bootstrap` token (six-hour validity); deny missing or invalid tokens. The credential lives in EC2 user data and is not embedded in the archive. Restrict access to EC2 user data and redact it from logs.

## Renewal and cattle-model replacement

- Rebuild and replace nodes from a fresh complete bundle at least every 60 days, and earlier if the node certificate has less than 30 days remaining. Do not renew certificates in place on nodes.
- Monitor CA and orchestrator client expiry daily. Alert at 90/60/30 days for the CA and 30/14/7 days for the client; alert at 30/14/7 days for node server certificates. Block new bundle publication if a certificate is invalid or expires within seven days.
- Replacement requires a verified bundle and fresh provisioning; simply waking a stopped EC2 instance does not rerun cloud-init.

## Compromise and revocation

- Compromised node key: terminate the node, invalidate its bundle, rotate its application secret, and provision a replacement. Because the current node Nginx trusts any client certificate issued by the CA, **node server keys must not be issued with clientAuth EKU**.
- Compromised orchestrator client key: stop remote DevOps operations, replace the orchestrator client certificate, and re-provision nodes with a new trust boundary or explicit certificate pinning/revocation enforcement. Merely issuing a new client cert does not revoke the old one.
- Compromised CA key: immediately disable DevOps access; create a new CA through a controlled rotation; replace orchestrator credentials and all nodes. Never auto-rotate a compromised CA.
- CA rollover requires an explicit two-phase trust migration or full coordinated cattle replacement. The existing code does not implement certificate revocation lists or OCSP; do not claim immediate leaf revocation until it does.

## Release gates

Before booting a node, confirm: deployed orchestrator source matches the intended Git revision; CA persistence and file permissions are correct; orchestrator client certificate and key match; bundle contains both MCP domains, a valid node leaf and **no CA key**; `nginx -t` passes; node DevOps endpoint rejects requests without mTLS; authorized DevOps `tools/list` succeeds; TAKS Business `tools/list` succeeds using the node secret. Record bundle digest, issuance date, expiry, and node identity in release evidence.

## Current limitation

The present implementation issues certificates but does not implement revocation, automatic fleet replacement, renewal alerts, or controlled CA rollover. These require separate operational work before unattended production operation.
