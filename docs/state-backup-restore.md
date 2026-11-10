# Preserving TAK node state across replacement

The operator API creates a node backup with `POST /api/v2/nodes/{fqdn}/backup`.
Supply the buckets `users`, `certs`, `cot_state`, `config`, `takctl_state`,
`martine_state`, and `documents`. The archive and manifest are stored under the
unit's private `backups/{backup_id}` directory on the orchestrator. The archive
contains credentials and private keys: its mode is 0600, and the directory is 0700.

`POST /api/v2/units/{unit}/backups/{backup_id}/select-restore` selects that archive.
Bundle validation checks component checksums, unit identity, PostgreSQL dump
format, and archive paths. Building the launch bundle embeds the archive and its
SHA-256. An explicitly selected corrupt or unsupported backup fails the launch.
A unit without a selection still launches with fresh state.

Fresh-node provisioning restores files before certificate generation, preserving
the CA, issued certificates, keystore passwords, and both TAKCTL state roots.
After LDAP initialization, and before TAK starts, it restores LDAP using logical
`slapcat`/`slapadd` and restores the complete CoT database using `pg_dump -Fc` and
`pg_restore`. Service code and dependencies come from the new bundle. Runtime
configuration is preserved; this includes the currently selected voice model.

The root-owned `/usr/local/libexec/taks-state-backup` supports only fixed named
backup operations. Its sudo rules do not allow arbitrary tar paths or commands.
The installer installs this helper for future nodes. An existing node that lacks
it needs the reviewed one-time bridge installer; it updates the backup API,
installs the helper and exact sudo rules, checks inventory access as `tak`, and
restarts TAKCTL. It does not replace the node or alter directory/database data.
The orchestrator serves the bridge source at `/bootstrap/state-backup-bridge.py`.

`GET /api/orchestrator/backup-inventory`, authenticated with the node bridge
secret, reports directory usernames, certificate fingerprints, PostgreSQL row
counts, and restore phase receipts. Compare the original backup inventory with
the replacement. Counts may increase once live TAK traffic resumes.

Format 1 archives containing raw live LDAP files are not silently restored.
Create a format 2 backup with the fixed helper. Individual LDAP and PostgreSQL
exports are consistent snapshots; this is not a distributed transaction across
all services. The current implementation targets the same TAK/LDAP/PostgreSQL
versions and the same unit identity. PostgreSQL roles are provisioned by the
installer; before restoring ACLs, the configured TAKCTL reader role is created
without login privileges if missing. The normal installer then applies its
managed login credential. The CoT dump preserves database ownership and ACLs.
