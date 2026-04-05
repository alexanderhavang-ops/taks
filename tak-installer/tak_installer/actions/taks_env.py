from __future__ import annotations

from pathlib import Path

from tak_installer.util import log


BOOTSTRAP_ROOT = Path("/etc/taks-bootstrap.d")
BOOTSTRAP_NODE_ENV = BOOTSTRAP_ROOT / "node.env"
BOOTSTRAP_CONFIG_D = BOOTSTRAP_ROOT / "config.d"
BOOTSTRAP_SECRETS_D = BOOTSTRAP_ROOT / "secrets.d"


def _pick(ctx, *keys: str) -> str:
    for k in keys:
        v = (ctx.env.get(k) or "").strip()
        if v:
            return v
    return ""


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k:
            out[k] = v
    return out


def _parse_simple_kv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k:
            out[k] = v
    return out


def _write_env_file(path: Path, data: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = ["# Managed by tak-installer"]
    for k in sorted(data.keys()):
        rows.append(f"{k}={data[k]}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    path.chmod(0o600)


def _write_simple_kv(path: Path, data: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [f"{k} = {v}" for k, v in data.items()]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    path.chmod(0o600)


def _merge_env_file(path: Path, updates: dict[str, str]) -> bool:
    cur = _parse_env_file(path)
    changed = False
    for k, v in updates.items():
        v = str(v or "").strip()
        if not v:
            continue
        if cur.get(k) != v:
            cur[k] = v
            changed = True
    if changed:
        _write_env_file(path, cur)
    return changed


def _merge_simple_kv(path: Path, updates: dict[str, str]) -> bool:
    cur = _parse_simple_kv(path)
    changed = False
    for k, v in updates.items():
        v = str(v or "").strip()
        if not v:
            continue
        if cur.get(k) != v:
            cur[k] = v
            changed = True
    if changed:
        _write_simple_kv(path, cur)
    return changed


def apply(ctx) -> None:
    """
    Persist orchestrator/bootstrap overrides into one canonical bootstrap area:

      /etc/taks-bootstrap.d/node.env
      /etc/taks-bootstrap.d/config.d/*.conf
      /etc/taks-bootstrap.d/secrets.d/*.conf

    This area is later materialized into TAKS runtime config/secrets by
    takctl-config. Files here are partial overlays; callers only need to set
    the specific fields they want to override.
    """
    BOOTSTRAP_CONFIG_D.mkdir(parents=True, exist_ok=True)
    BOOTSTRAP_SECRETS_D.mkdir(parents=True, exist_ok=True)

    node_updates = {
        "TAKS_FQDN": _pick(ctx, "FQDN", "TAKS_FQDN"),
        "TAKS_NODE_CERT_MODEL": _pick(ctx, "TAKS_NODE_CERT_MODEL"),
        "LE_EMAIL": _pick(ctx, "LE_EMAIL"),
    }
    if _merge_env_file(BOOTSTRAP_NODE_ENV, node_updates):
        log.info("taks-env: updated %s", BOOTSTRAP_NODE_ENV)
    else:
        log.info("taks-env: no node bootstrap env changes")

    config_updates: dict[str, dict[str, str]] = {
        "certs.conf": {
            "cert_country": _pick(ctx, "TAKS_CERT_COUNTRY", "CERT_COUNTRY"),
            "cert_state": _pick(ctx, "TAKS_CERT_STATE", "CERT_STATE"),
            "cert_city": _pick(ctx, "TAKS_CERT_CITY", "CERT_CITY"),
            "cert_organization": _pick(ctx, "TAKS_CERT_ORGANIZATION", "CERT_ORGANIZATION"),
            "cert_organizational_unit": _pick(ctx, "TAKS_CERT_ORGANIZATIONAL_UNIT", "CERT_ORGANIZATIONAL_UNIT"),
        },
        "llm.conf": {
            "aws_region": _pick(ctx, "AWS_REGION"),
            "bedrock_model_id": _pick(ctx, "BEDROCK_MODEL_ID"),
            "llm_model": _pick(ctx, "TAKS_LLM_MODEL", "LLM_MODEL"),
        },
        "martine.conf": {
            "martine_username": _pick(ctx, "MARTINE_USERNAME"),
            "martine_groups_rw": _pick(ctx, "MARTINE_GROUPS_RW"),
            "martine_groups_in": _pick(ctx, "MARTINE_GROUPS_IN"),
            "martine_groups_out": _pick(ctx, "MARTINE_GROUPS_OUT"),
        },
    }

    for name, updates in config_updates.items():
        if _merge_simple_kv(BOOTSTRAP_CONFIG_D / name, updates):
            log.info("taks-env: updated %s", BOOTSTRAP_CONFIG_D / name)

    secret_updates: dict[str, dict[str, str]] = {
        "bedrock.conf": {
            "bedrock_api_key": _pick(ctx, "BEDROCK_API_KEY"),
        },
        "ses.conf": {
            "ses_smtp_username": _pick(ctx, "SES_SMTP_USERNAME"),
            "ses_smtp_password": _pick(ctx, "SES_SMTP_PASSWORD"),
        },
    }

    for name, updates in secret_updates.items():
        if _merge_simple_kv(BOOTSTRAP_SECRETS_D / name, updates):
            log.info("taks-env: updated %s", BOOTSTRAP_SECRETS_D / name)


class _Action:
    ID = "taks-env"

    def inspect(self, ctx) -> int:
        print(f"Inspecting {self.ID} action...")
        return 0

    def apply(self, ctx) -> int:
        print(f"Applying {self.ID} action...")
        apply(ctx)
        return 0


ACTION = _Action()
