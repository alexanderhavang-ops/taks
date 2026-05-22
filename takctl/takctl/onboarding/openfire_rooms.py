from __future__ import annotations

import base64
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from takctl.config import load_config
from takctl.onboarding.channels import derive_channel_sets

OPENFIRE_DB = Path("/var/lib/openfire/embedded-db/openfire.script")
OPENFIRE_LOG = Path("/var/lib/openfire/embedded-db/openfire.log")
JOB_DIR = Path("/opt/tak/takctl-state/onboarding/xmpp_bookmarks/done")

_VALID_USER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


def _read_kv(paths: list[Path]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in paths:
        if not p.exists() or not p.is_file():
            continue
        for raw in p.read_text(errors="replace").splitlines():
            s = raw.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _cfg_get(cfg: dict[str, Any], *keys: str, default: str = "") -> str:
    for k in keys:
        v = str(cfg.get(k) or "").strip()
        if v:
            return v
    return default


def _node_context(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    pid = _cfg_get(cfg, "default_policy_id", default="fro")

    unit = _cfg_get(
        cfg,
        "unit",
        "node_unit",
        "unit_name",
        "organization",
        "cert_organization",
        default="",
    )

    if not unit:
        fqdn = _cfg_get(cfg, "node_fqdn", "fqdn", "tak_host", default="")
        if fqdn:
            unit = fqdn.split(".", 1)[0]

    if not unit:
        unit = "default"

    return {
        "policy_id": pid,
        "unit": unit,
        "node_unit": unit,
        "organization": unit,
        "cert_organization": unit,
    }


def _sql_quote(v: str) -> str:
    return "'" + str(v).replace("'", "''") + "'"


def _norm_room_name(v: str) -> str:
    s = str(v or "").strip().lower()
    s = re.sub(r"[^a-z0-9-]+", "-", s).strip("-")
    return s


def _split_sql_values(s: str) -> list[str]:
    out: list[str] = []
    cur: list[str] = []
    in_q = False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "'":
            cur.append(ch)
            if in_q and i + 1 < len(s) and s[i + 1] == "'":
                cur.append("'")
                i += 2
                continue
            in_q = not in_q
            i += 1
            continue
        if ch == "," and not in_q:
            out.append("".join(cur).strip())
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    out.append("".join(cur).strip())
    return out


def _unquote_sql(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == "'" and v[-1] == "'":
        return v[1:-1].replace("''", "'")
    return v


def _hsql_date() -> str:
    return f"{int(time.time() * 1000):015d}"


def _extract_create_table_cols(text: str, table: str) -> list[str]:
    m = re.search(
        rf"CREATE\s+\w+\s+TABLE\s+PUBLIC\.{re.escape(table)}\((.*?)\)\s*$",
        text,
        flags=re.I | re.M | re.S,
    )
    if not m:
        raise RuntimeError(f"could not find CREATE TABLE PUBLIC.{table}")

    inner = m.group(1)
    cols: list[str] = []
    depth = 0
    cur: list[str] = []

    for ch in inner:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1

        if ch == "," and depth == 0:
            part = "".join(cur).strip()
            cur = []
            if part and not part.upper().startswith("CONSTRAINT "):
                cols.append(part.split()[0].upper())
            continue

        cur.append(ch)

    part = "".join(cur).strip()
    if part and not part.upper().startswith("CONSTRAINT "):
        cols.append(part.split()[0].upper())

    return cols


def _insert_row(table: str, cols: list[str], values_by_col: dict[str, object]) -> str:
    vals: list[str] = []
    missing: list[str] = []

    for c in cols:
        if c not in values_by_col:
            missing.append(c)
            continue

        v = values_by_col[c]
        if v is None:
            vals.append("NULL")
        elif isinstance(v, int):
            vals.append(str(v))
        else:
            vals.append(_sql_quote(str(v)))

    if missing:
        raise RuntimeError(f"missing values for {table}: {missing}; schema={cols}")

    return f"INSERT INTO {table} VALUES(" + ",".join(vals) + ")"


def derive_policy_room_labels(ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    ctx = ctx or _node_context()
    sets = derive_channel_sets(ctx)

    return {
        "ctx": ctx,
        "available": list(sets.get("available") or []),
        "default": list(sets.get("default") or []),
    }


def _current_openfire_rooms(text: str, domain: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for line in text.splitlines():
        if "INSERT INTO OFMUCROOM VALUES(" not in line:
            continue
        inner = line.split("VALUES(", 1)[1]
        if inner.endswith(")"):
            inner = inner[:-1]
        vals = _split_sql_values(inner)
        if len(vals) < 6:
            continue
        local = _unquote_sql(vals[4]).strip().lower()
        natural = _unquote_sql(vals[5]).strip() or local
        if local:
            out[local] = {
                "name": natural,
                "jid": f"{local}@conference.{domain}",
                "autojoin": True,
                "nick": None,
            }
    return out


def seed_openfire_rooms(
    *,
    ctx: dict[str, Any] | None = None,
    remove_unknown_unit: bool = True,
    db_path: Path = OPENFIRE_DB,
    log_path: Path = OPENFIRE_LOG,
) -> dict[str, Any]:
    cfg = load_config()
    ctx = ctx or _node_context(cfg)
    pid = str(ctx.get("policy_id") or _cfg_get(cfg, "default_policy_id", default="fro"))

    domain = _cfg_get(cfg, "xmpp_domain", "openfire_domain", "node_fqdn", "fqdn")
    if not domain:
        domain = "localhost"

    derived = derive_policy_room_labels(ctx)
    raw_channels = list(derived.get("available") or derived.get("default") or [])

    rooms: list[tuple[str, str]] = []
    seen: set[str] = set()
    for label in raw_channels:
        local = _norm_room_name(label)
        natural = str(label or "").strip()
        if not local or local in seen:
            continue
        seen.add(local)
        rooms.append((local, natural))

    if not rooms:
        return {
            "ok": False,
            "policy_id": pid,
            "ctx": ctx,
            "created_count": 0,
            "created_rooms": [],
            "error": "no policy channels derived",
        }

    text = db_path.read_text(encoding="utf-8", errors="replace")
    cols = _extract_create_table_cols(text, "OFMUCROOM")

    svc_id = 1
    m = re.search(r"INSERT INTO OFMUCSERVICE VALUES\((\d+),'conference'", text, flags=re.I)
    if m:
        svc_id = int(m.group(1))

    existing_names: set[str] = set()
    existing_ids: list[int] = []
    for line in text.splitlines():
        if "INSERT INTO OFMUCROOM VALUES(" not in line:
            continue
        inner = line.split("VALUES(", 1)[1]
        if inner.endswith(")"):
            inner = inner[:-1]
        vals = _split_sql_values(inner)
        if len(vals) >= 5:
            try:
                existing_ids.append(int(vals[1]))
            except Exception:
                pass
            existing_names.add(_unquote_sql(vals[4]).lower())

    desired_names = {name for name, _ in rooms}

    if remove_unknown_unit and "org-unknown-unit" in existing_names and "org-unknown-unit" not in desired_names:
        kept_lines = [
            line for line in text.splitlines()
            if "INSERT INTO OFMUCROOM VALUES(" not in line
            or "'org-unknown-unit'" not in line
        ]
        text = "\n".join(kept_lines) + "\n"
        existing_names.discard("org-unknown-unit")

    next_id = max(existing_ids or [0]) + 1
    now = _hsql_date()
    new_rows: list[str] = []

    for name, natural in rooms:
        if name in existing_names:
            continue

        values = {
            "SERVICEID": svc_id,
            "ROOMID": next_id,
            "CREATIONDATE": now,
            "MODIFICATIONDATE": now,
            "NAME": name,
            "NATURALNAME": natural,
            "DESCRIPTION": f"TAKS policy {pid} channel {natural}",
            "LOCKEDDATE": None,
            "EMPTYDATE": None,
            "CANCHANGESUBJECT": 1,
            "MAXUSERS": 0,
            "PUBLICROOM": 1,
            "MODERATED": 0,
            "MEMBERSONLY": 0,
            "CANINVITE": 1,
            "ROOMPASSWORD": None,
            "CANDISCOVERJID": 1,
            "LOGENABLED": 1,
            "RETIREONDELETION": 0,
            "PRESERVEHISTONDEL": 0,
            "SUBJECT": None,
            "ROLESTOBROADCAST": 7,
            "USERESERVEDNICK": 0,
            "CANCHANGENICK": 1,
            "CANREGISTER": 1,
            "ALLOWPM": 0,
            "FMUCENABLED": 0,
            "FMUCOUTBOUNDNODE": None,
            "FMUCOUTBOUNDMODE": 0,
            "FMUCINBOUNDNODES": None,
        }
        new_rows.append(_insert_row("OFMUCROOM", cols, values))
        existing_names.add(name)
        next_id += 1

    if new_rows or remove_unknown_unit:
        svc_matches = list(re.finditer(r"INSERT INTO OFMUCSERVICE VALUES\(.*?\)\n?", text))
        insert_at = svc_matches[-1].end() if svc_matches else None
        if insert_at is None:
            ins_matches = list(re.finditer(r"INSERT INTO .*?\n", text))
            insert_at = ins_matches[-1].end() if ins_matches else len(text)

        if new_rows:
            block = "".join(row + "\n" for row in new_rows)
            text = text[:insert_at] + block + text[insert_at:]

        db_path.write_text(text, encoding="utf-8")

        if log_path.exists():
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            kept = [
                line for line in log_text.splitlines()
                if "INSERT INTO OFMUCROOM VALUES(" not in line
                and "org-unknown-unit" not in line
            ]
            log_path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")

    final_rooms = _current_openfire_rooms(db_path.read_text(errors="replace"), domain)

    return {
        "ok": True,
        "policy_id": pid,
        "ctx": ctx,
        "domain": domain,
        "derived_available": raw_channels,
        "created_count": len(new_rows),
        "created_rooms": [
            _unquote_sql(_split_sql_values(row.split("VALUES(", 1)[1][:-1])[4])
            for row in new_rows
        ],
        "openfire_rooms": sorted(final_rooms),
    }


def _parse_ldif_records(text: str) -> list[dict[str, list[str]]]:
    records: list[dict[str, list[str]]] = []
    cur: dict[str, list[str]] = {}

    unfolded: list[str] = []
    for raw in text.splitlines():
        if raw.startswith(" ") and unfolded:
            unfolded[-1] += raw[1:]
        else:
            unfolded.append(raw)

    for raw in unfolded:
        line = raw.rstrip("\n")
        if not line:
            if cur:
                records.append(cur)
            cur = {}
            continue

        if "::" in line:
            k, v = line.split("::", 1)
            try:
                val = base64.b64decode(v.strip()).decode("utf-8", errors="replace").strip()
            except Exception:
                val = ""
        elif ":" in line:
            k, v = line.split(":", 1)
            val = v.strip()
        else:
            continue

        cur.setdefault(k.strip(), []).append(val)

    if cur:
        records.append(cur)

    return records


def _ldap_users(cfg: dict[str, Any]) -> list[dict[str, str]]:
    secret_cfg = _read_kv([
        Path("/opt/tak/tools/takctl/secrets.d/ldap.conf"),
        Path("/etc/taks/ldap-secrets.conf"),
        Path("/etc/taks/ldap.conf"),
        Path("/etc/taks-bootstrap.d/config.d/ldap.conf"),
    ])

    base_dn = _cfg_get(cfg, "ldap_base_dn", default="dc=taks,dc=local")
    uri = _cfg_get(cfg, "ldap_uri", default="ldap://127.0.0.1:389")
    bind_dn = _cfg_get(
        cfg,
        "ldap_service_account_dn",
        "ldap_admin_dn",
        default=f"cn=taksvc,ou=services,{base_dn}",
    )
    bind_pw = (
        secret_cfg.get("ldap_service_account_password")
        or secret_cfg.get("ldap_bind_password")
        or secret_cfg.get("ldap_admin_password")
        or secret_cfg.get("ldap_password")
        or _cfg_get(cfg, "ldap_service_account_password", "ldap_bind_password", "ldap_admin_password", "ldap_password")
    )

    if not bind_pw:
        raise RuntimeError("could not determine LDAP bind password")

    cmd = [
        "ldapsearch",
        "-LLL",
        "-o", "ldif-wrap=no",
        "-x",
        "-H", uri,
        "-D", bind_dn,
        "-w", bind_pw,
        "-b", base_dn,
        "(&(objectClass=inetOrgPerson)(uid=*))",
        "uid", "cn", "displayName",
    ]

    res = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0:
        raise RuntimeError(f"ldapsearch failed rc={res.returncode}: {res.stderr.strip()}")

    users: list[dict[str, str]] = []
    for rec in _parse_ldif_records(res.stdout):
        uid = (rec.get("uid") or [""])[0].strip().lower()
        cn = (rec.get("cn") or rec.get("displayName") or [uid])[0].strip()
        if _VALID_USER_RE.match(uid):
            users.append({"uid": uid, "cn": cn or uid})

    return users


def clean_invalid_jobs(job_dir: Path = JOB_DIR) -> dict[str, Any]:
    job_dir.mkdir(parents=True, exist_ok=True)
    removed: list[str] = []

    for p in sorted(job_dir.glob("*.json")):
        try:
            job = json.loads(p.read_text(errors="replace"))
            username = str(job.get("username") or "").strip().lower()
            target = str(job.get("target_jid") or "").strip().lower()
            if not _VALID_USER_RE.match(username):
                raise ValueError(f"bad username={username!r}")
            if not target.startswith(username + "@"):
                raise ValueError(f"target mismatch target={target!r} username={username!r}")
        except Exception:
            removed.append(str(p))
            p.unlink(missing_ok=True)

    return {"removed": removed, "removed_count": len(removed)}


def backfill_invite_jobs(job_dir: Path = JOB_DIR) -> dict[str, Any]:
    cfg = load_config()
    ctx = _node_context(cfg)
    seeded = seed_openfire_rooms(ctx=ctx)
    domain = _cfg_get(cfg, "xmpp_domain", "openfire_domain", "node_fqdn", "fqdn")
    if not domain:
        raise RuntimeError("could not determine XMPP domain")

    text = OPENFIRE_DB.read_text(errors="replace")
    rooms_by_local = _current_openfire_rooms(text, domain)

    labels = derive_policy_room_labels(ctx)
    default_labels = list(labels.get("default") or [])
    available_labels = list(labels.get("available") or [])

    default_rooms = []
    for label in default_labels:
        local = _norm_room_name(label)
        if local in rooms_by_local:
            default_rooms.append(rooms_by_local[local])

    available_rooms = []
    for label in available_labels:
        local = _norm_room_name(label)
        if local in rooms_by_local:
            available_rooms.append(rooms_by_local[local])

    if not default_rooms:
        if "ledning" in rooms_by_local:
            default_rooms = [rooms_by_local["ledning"]]
        elif rooms_by_local:
            default_rooms = [rooms_by_local[sorted(rooms_by_local)[0]]]

    if not available_rooms:
        available_rooms = [rooms_by_local[k] for k in sorted(rooms_by_local)]

    if not default_rooms:
        raise RuntimeError("no default room available")

    job_dir.mkdir(parents=True, exist_ok=True)
    cleanup = clean_invalid_jobs(job_dir)

    skip = {"admin", "martine", "taksvc", "openfire"}
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    written: list[str] = []

    for u in _ldap_users(cfg):
        username = u["uid"]
        if username in skip:
            continue

        target_jid = f"{username}@{domain}".lower()
        nick = u.get("cn") or username

        conferences = []
        for c in default_rooms:
            cc = dict(c)
            cc["nick"] = nick
            conferences.append(cc)

        available_conferences = []
        for c in available_rooms:
            cc = dict(c)
            cc["nick"] = nick
            available_conferences.append(cc)

        job = {
            "ok": True,
            "source": "taks-openfire-policy-backfill",
            "created_at": now,
            "updated_at": now,
            "policy_id": str(ctx.get("policy_id") or "fro"),
            "username": username,
            "target_jid": target_jid,
            "domain": domain,
            "conferences": conferences,
            "available_conferences": available_conferences,
            "fallback_default": True,
        }

        path = job_dir / f"{username}.json"
        path.write_text(json.dumps(job, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        written.append(username)

    return {
        "ok": True,
        "seeded": seeded,
        "cleanup": cleanup,
        "domain": domain,
        "ctx": ctx,
        "default_rooms": [c["jid"] for c in default_rooms],
        "available_rooms": [c["jid"] for c in available_rooms],
        "written_count": len(written),
        "written_users": written,
    }


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Seed OpenFire MUC rooms and XMPP invite jobs from TAKS policy channels.")
    ap.add_argument("command", choices=["derive", "seed-rooms", "backfill-jobs", "clean-jobs"])
    args = ap.parse_args()

    if args.command == "derive":
        print(json.dumps(derive_policy_room_labels(), ensure_ascii=False, indent=2, sort_keys=True))
    elif args.command == "seed-rooms":
        print(json.dumps(seed_openfire_rooms(), ensure_ascii=False, indent=2, sort_keys=True))
    elif args.command == "backfill-jobs":
        print(json.dumps(backfill_invite_jobs(), ensure_ascii=False, indent=2, sort_keys=True))
    elif args.command == "clean-jobs":
        print(json.dumps(clean_invalid_jobs(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
