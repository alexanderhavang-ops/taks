#!/usr/bin/env bash
set -euo pipefail

# Narrow sudoers permissions needed by takctl orchestrator-triggered backups.
# tar: read root-owned runtime files such as TAK cert/private-key material.
# pg_dump: dump TAK postgres state as the local postgres superuser.

install -d -m 0755 /etc/sudoers.d

tmp="$(mktemp)"
cat > "$tmp" <<'EOF'
# Installed by TAKS for orchestrator-triggered node backups.
tak ALL=(root) NOPASSWD: /usr/bin/tar
tak ALL=(postgres) NOPASSWD: /usr/bin/pg_dump
EOF

chmod 0440 "$tmp"
visudo -cf "$tmp"
install -o root -g root -m 0440 "$tmp" /etc/sudoers.d/takctl-orchestrator-backup
rm -f "$tmp"
