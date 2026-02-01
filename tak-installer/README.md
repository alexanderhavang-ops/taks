TAK Installer (tak-installer)

Status (Feb 2026)

No installer implementation exists yet in this repository.

Strategy: tak-installer apply will be the single source of truth for converging a node.

Inputs (planned)

Site/battalion parameters (non-secret)

Secrets via env or root-readable files

What apply will converge (planned)

takctl runtime tree under /opt/tak/tools/takctl

takctl config file rendering

systemd units (e.g. takctl-web.service)

nginx config for enrollment + takctl WebUI

users/groups + permissions

What exists in git today (infra templates)

infra/systemd/takctl-web.service

infra/nginx/server-443.conf.example

infra/nginx/takctl-web.conf

infra/nginx/local/* (site-specific; will be templated)

infra/notes/architecture.md
