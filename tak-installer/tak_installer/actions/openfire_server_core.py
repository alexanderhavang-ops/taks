from __future__ import annotations

import hashlib
import json
import os
import secrets
import string
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from tak_installer.engine import Context
from tak_installer.runtime_state import get_fqdn
from takctl.onboarding.policy import Policy
from takctl.onboarding.voice_topology import derive_voice_topology

PACKAGE = "openfire"
SERVICE = "openfire"
DEFAULT_VERSION = "5.0.4"
CACHE_DIR = Path("/opt/tak/cache/openfire")
CONFIG = Path("/etc/openfire/openfire.xml")
EMBEDDED_DB_SCRIPT = Path("/var/lib/openfire/embedded-db/openfire.script")

SECRET_DIR = Path("/opt/tak/tools/takctl/secrets.d")
SECRET_FILE = SECRET_DIR / "openfire.conf"

BOOTSTRAP_NODE_CONF = Path("/etc/taks-bootstrap.d/config.d/node.conf")
TAKCTL_NODE_CONF = Path("/opt/tak/tools/takctl/conf.d/node.conf")

CONFIG_DIRS = [
    Path("/etc/taks-bootstrap.d/config.d"),
    Path("/etc/taks"),
    Path("/opt/tak/tools/takctl/conf.d"),
    Path("/opt/tak/tools/martine/conf.d"),
]


def _env_first(env: dict[str, str], *keys: str, default: str = "") -> str:
    for key in keys:
        v = str(env.get(key, "") or "").strip()
        if v:
            return v
    return default


def _truthy(v: str) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


def _systemctl_state(arg: str) -> str:
    p = subprocess.run(
        ["systemctl", arg, SERVICE],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return str(p.stdout or "").strip()


def _pkg_version() -> str:
    p = subprocess.run(
        ["dpkg-query", "-W", "-f=${Version}", PACKAGE],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if p.returncode != 0:
        return ""
    return str(p.stdout or "").strip()


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if check and p.returncode != 0:
        raise RuntimeError(
            f"command failed rc={p.returncode}:\n{' '.join(cmd)}\n\n{p.stdout}"
        )
    if (p.stdout or "").strip():
        print((p.stdout or "").strip())
    return p


def _strip_quotes(v: str) -> str:
    s = str(v or "").strip()
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        return s[1:-1]
    return s


def _read_simple_kv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists() or not path.is_file():
        return out

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return out

    for raw in lines:
        s = str(raw or "").strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        key = str(k or "").strip()
        val = _strip_quotes(v)
        if key:
            out[key] = val
    return out


def _read_config_files() -> dict[str, str]:
    out: dict[str, str] = {}
    for root in CONFIG_DIRS:
        if not root.exists() or not root.is_dir():
            continue
        for path in sorted(root.glob("*.conf")):
            out.update(_read_simple_kv(path))
    return out


def _read_secret_cfg() -> dict[str, str]:
    return _read_simple_kv(SECRET_FILE)


def _write_secret_cfg(values: dict[str, str]) -> None:
    merged = _read_secret_cfg()
    merged.update({k: str(v or "").strip() for k, v in values.items() if str(k or "").strip()})

    lines = [
        "# managed by tak-installer action openfire_server.core",
    ]
    for k in sorted(merged):
        v = str(merged.get(k, "") or "")
        lines.append(f'{k}="{v}"')

    tmp = Path(f"/tmp/openfire.conf.{os.getpid()}")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")

    try:
        _run(["sudo", "install", "-d", "-m", "0750", str(SECRET_DIR)])
        _run([
            "sudo", "install",
            "-o", "root",
            "-g", "tak",
            "-m", "0640",
            str(tmp),
            str(SECRET_FILE),
        ])
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _resolve_fqdn_from_files() -> str:
    for path in (BOOTSTRAP_NODE_CONF, TAKCTL_NODE_CONF):
        vals = _read_simple_kv(path)
        for key in ("node_fqdn", "fqdn"):
            v = str(vals.get(key, "") or "").strip()
            if v:
                return v
    return ""


def _strong_password(n: int = 24) -> str:
    letters = string.ascii_letters + string.digits + "#%"
    return "OFadmin-" + "".join(secrets.choice(letters) for _ in range(max(8, n - 8)))



def _generate_openfire_admin_password_for_install() -> str:
    alphabet = string.ascii_letters + string.digits + "#%"
    return "OFadmin-" + "".join(secrets.choice(alphabet) for _ in range(20))


def _persist_openfire_admin_password_for_install(password: str) -> None:
    password = str(password or "").strip()
    if not password:
        raise RuntimeError("openfire_server.core: cannot persist empty admin password")

    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)

    existing_lines: list[str] = []
    found = False

    if SECRET_FILE.exists():
        try:
            existing_lines = SECRET_FILE.read_text(encoding="utf-8").splitlines()
        except Exception:
            existing_lines = []

    out_lines: list[str] = []
    for raw in existing_lines:
        line = str(raw)
        stripped = line.strip()
        if stripped.startswith("openfire_admin_password="):
            out_lines.append(f"openfire_admin_password={password}")
            found = True
        else:
            out_lines.append(line)

    if not found:
        if out_lines and out_lines[-1].strip():
            out_lines.append("")
        out_lines.append("# managed by tak-installer action openfire_server.core")
        out_lines.append(f"openfire_admin_password={password}")

    tmp = SECRET_FILE.with_name(SECRET_FILE.name + ".tmp")
    tmp.write_text("\n".join(out_lines).rstrip() + "\n", encoding="utf-8")
    os.chmod(tmp, 0o640)
    os.replace(tmp, SECRET_FILE)

def _cfg(ctx: Context) -> dict[str, str]:
    env = _read_config_files()
    env.update(dict(ctx.env or {}))
    sec = _read_secret_cfg()

    version = _env_first(
        env,
        "openfire_version",
        "OPENFIRE_VERSION",
        default=DEFAULT_VERSION,
    )

    enabled = _truthy(
        _env_first(
            env,
            "openfire_enabled",
            "OPENFIRE_ENABLED",
            default="true",
        )
    )

    admin_password = _env_first(
        env,
        "openfire_admin_password",
        "OPENFIRE_ADMIN_PASSWORD",
        default=str(sec.get("openfire_admin_password", "") or "").strip(),
    )

    admin_email = _env_first(
        env,
        "openfire_admin_email",
        "OPENFIRE_ADMIN_EMAIL",
        default=str(sec.get("openfire_admin_email", "") or "").strip(),
    )

    admin_interface = _env_first(
        env,
        "openfire_admin_interface",
        "OPENFIRE_ADMIN_INTERFACE",
        default=str(sec.get("openfire_admin_interface", "") or "").strip() or "127.0.0.1",
    )

    fqdn = ""
    try:
        fqdn = str(get_fqdn() or "").strip()
    except Exception:
        fqdn = ""

    if not fqdn:
        fqdn = _resolve_fqdn_from_files()

    fqdn = _env_first(
        env,
        "node_fqdn",
        "NODE_FQDN",
        "openfire_domain",
        "OPENFIRE_DOMAIN",
        default=fqdn,
    )

    if not admin_email and fqdn:
        admin_email = f"admin@{fqdn}"

    xmpp_client_cert_policy = _env_first(
        env,
        "openfire_xmpp_client_cert_policy",
        "OPENFIRE_XMPP_CLIENT_CERT_POLICY",
        default="wanted",
    ).strip().lower()

    if xmpp_client_cert_policy not in ("disabled", "wanted", "needed"):
        xmpp_client_cert_policy = "wanted"

    backing_user_store = _env_first(
        env,
        "backing_user_store",
        "BACKING_USER_STORE",
        default="userauthfile",
    ).strip().lower()

    ldap_uri = _env_first(env, "ldap_uri", "LDAP_URI", default="ldap://127.0.0.1:389").strip()
    ldap_base_dn = _env_first(env, "ldap_base_dn", "LDAP_BASE_DN", default="dc=taks,dc=local").strip()
    ldap_people_ou = _env_first(env, "ldap_people_ou", "LDAP_PEOPLE_OU", default="people").strip()
    ldap_groups_ou = _env_first(env, "ldap_groups_ou", "LDAP_GROUPS_OU", default="groups").strip()
    ldap_service_account_dn = _env_first(
        env,
        "ldap_service_account_dn",
        "LDAP_SERVICE_ACCOUNT_DN",
        default=f"cn=taksvc,ou=services,{ldap_base_dn}",
    ).strip()
    ldap_service_account_password = _env_first(
        env,
        "ldap_service_account_password",
        "LDAP_SERVICE_ACCOUNT_PASSWORD",
        default="",
    ).strip()

    return {
        "enabled": "true" if enabled else "false",
        "version": version,
        "deb_url": f"https://download.igniterealtime.org/openfire/openfire_{version}_all.deb",
        "admin_password": admin_password,
        "admin_email": admin_email,
        "admin_interface": admin_interface,
        "fqdn": fqdn,
        "xmpp_client_cert_policy": xmpp_client_cert_policy,
        "backing_user_store": backing_user_store,
        "ldap_uri": ldap_uri,
        "ldap_base_dn": ldap_base_dn,
        "ldap_people_ou": ldap_people_ou,
        "ldap_groups_ou": ldap_groups_ou,
        "ldap_service_account_dn": ldap_service_account_dn,
        "ldap_service_account_password": ldap_service_account_password,
    }


def _ensure_secret_defaults(cfg: dict[str, str]) -> dict[str, str]:
    changed: dict[str, str] = {}
    out = dict(cfg)

    if not str(out.get("admin_password", "") or "").strip():
        out["admin_password"] = _strong_password()
        changed["openfire_admin_password"] = out["admin_password"]

    if not str(out.get("admin_email", "") or "").strip() and str(out.get("fqdn", "") or "").strip():
        out["admin_email"] = f"admin@{out['fqdn']}"
        changed["openfire_admin_email"] = out["admin_email"]

    if not str(out.get("admin_interface", "") or "").strip():
        out["admin_interface"] = "127.0.0.1"
        changed["openfire_admin_interface"] = out["admin_interface"]

    if changed:
        _write_secret_cfg(changed)

    return out


def _setup_complete() -> bool:
    try:
        txt = CONFIG.read_text(encoding="utf-8")
    except Exception:
        return False
    compact = txt.lower().replace("\n", "").replace("\r", "").replace(" ", "")
    return "<setup>true</setup>" in compact


def _wait_for_setup_complete(timeout_s: int = 90) -> bool:
    deadline = time.time() + max(1, timeout_s)
    while time.time() < deadline:
        if _setup_complete():
            return True
        time.sleep(2)
    return _setup_complete()


def _ensure_embedded_db_auth_provider_consistency(cfg: dict[str, str]) -> bool:
    """Ensure OpenFire uses LDAP users/auth when TAKS backing_user_store=ldap.

    Fresh OpenFire/HSQLDB often has schema in openfire.log while openfire.script
    still contains only the DB prologue. In that state, managed rows must be
    written to the transaction log, not the script, or OpenFire will fail during
    replay with out-of-order INSERT statements.
    """
    if str(cfg.get("backing_user_store", "") or "").strip().lower() != "ldap":
        print("openfire_server.core: backing_user_store is not ldap; leaving OpenFire providers unchanged")
        return False

    code = r"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import json
import re
import shutil

db = Path("__DB_PATH__")
log = db.with_name("openfire.log")
cfg = __CFG_JSON__

if not db.exists():
    print(f"openfire_server.core: embedded DB script not present yet: {db}")
    print("CHANGED=0")
    raise SystemExit(0)

def sql_quote(v: str) -> str:
    return "'" + str(v).replace("'", "''") + "'"

def sql_unquote(v: str) -> str:
    return str(v).replace("''", "'")

def prop_line(k: str, v: str, encrypted: int = 0) -> str:
    return f"INSERT INTO OFPROPERTY VALUES({sql_quote(k)},{sql_quote(v)},{int(encrypted)},NULL)"

def insert_before_log_footer(text: str, block: str) -> str:
    footers = list(re.finditer(r"^\s*SET FILES LOG SIZE .*$", text, flags=re.M))
    if footers:
        pos = footers[-1].start()
        return text[:pos].rstrip() + "\n" + block + text[pos:]
    return text.rstrip() + "\n" + block

uri = urlparse(str(cfg.get("ldap_uri") or "ldap://127.0.0.1:389"))
scheme = (uri.scheme or "ldap").lower()
host = uri.hostname or "127.0.0.1"
port = str(uri.port or (636 if scheme == "ldaps" else 389))

base_dn = str(cfg.get("ldap_base_dn") or "dc=taks,dc=local").strip()
admin_dn = str(cfg.get("ldap_service_account_dn") or f"cn=taksvc,ou=services,{base_dn}").strip()
admin_pw = str(cfg.get("ldap_service_account_password") or "").strip()

props = {
    "provider.auth.className": "org.jivesoftware.openfire.ldap.LdapAuthProvider",
    "provider.user.className": "org.jivesoftware.openfire.ldap.LdapUserProvider",
    "provider.group.className": "org.jivesoftware.openfire.ldap.LdapGroupProvider",
    "ldap.host": host,
    "ldap.port": port,
    "ldap.baseDN": base_dn,
    "ldap.adminDN": admin_dn,
    "ldap.adminPassword": admin_pw,
    "ldap.usernameField": "uid",
    "ldap.nameField": "cn",
    "ldap.emailField": "mail",
    "ldap.searchFilter": "(uid={0})",
    "ldap.groupNameField": "cn",
    "ldap.groupMemberField": "member",
    "ldap.groupDescriptionField": "description",
    "ldap.groupSearchFilter": "(objectClass=groupOfNames)",
    "ldap.posixMode": "false",
    "ldap.connectionPoolEnabled": "true",
}

if scheme == "ldaps":
    props.update({
        "ldap.encryption": "ssl",
        "ldap.sslEnabled": "true",
        "ldap.startTlsEnabled": "false",
        "ldap.startTLSEnabled": "false",
    })
else:
    props.update({
        "ldap.encryption": "none",
        "ldap.sslEnabled": "false",
        "ldap.startTlsEnabled": "false",
        "ldap.startTLSEnabled": "false",
    })

managed_keys = set(props)

def strip_managed_props(text: str) -> str:
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.fullmatch(r"',0,NULL\)", stripped):
            continue
        m = re.match(r"INSERT INTO OFPROPERTY VALUES\('((?:''|[^'])*)',", stripped)
        if m and sql_unquote(m.group(1)) in managed_keys:
            continue
        out.append(line)
    return "\n".join(out) + "\n"

script_text = db.read_text(encoding="utf-8", errors="replace")
log_text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""

script_has_schema = re.search(r"CREATE\s+TABLE\s+(?:PUBLIC\.)?OFPROPERTY\b", script_text, re.I) is not None
log_has_schema = re.search(r"CREATE\s+TABLE\s+(?:PUBLIC\.)?OFPROPERTY\b", log_text, re.I) is not None

if script_has_schema:
    target = db
    old = script_text
    kind = "script"
elif log_has_schema:
    target = log
    old = log_text
    kind = "log"
else:
    print("openfire_server.core: OpenFire ofProperty schema not present yet; deferring LDAP DB repair")
    print("CHANGED=0")
    raise SystemExit(0)

s = strip_managed_props(old)
rows = [prop_line(k, v, 0) for k, v in props.items()]

if kind == "log":
    block = "/*C2*/SET SCHEMA PUBLIC\n" + "\n".join(rows) + "\nCOMMIT\n"
    new_s = insert_before_log_footer(s, block)
else:
    insert_at = None
    prop_rows = list(re.finditer(r"INSERT INTO OFPROPERTY VALUES\(.*?\)\n?", s))
    if prop_rows:
        insert_at = prop_rows[-1].end()
    if insert_at is None:
        schema_rows = list(re.finditer(r"CREATE\s+TABLE\s+(?:PUBLIC\.)?OFPROPERTY\(.*?\)\s*$", s, flags=re.I | re.M))
        insert_at = schema_rows[-1].end() if schema_rows else len(s)
    block = "".join(row + "\n" for row in rows)
    new_s = s[:insert_at] + "\n" + block + s[insert_at:]

if new_s == old:
    print("openfire_server.core: OpenFire LDAP provider/properties already consistent")
    print("CHANGED=0")
    raise SystemExit(0)

stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
backup = target.with_name(target.name + f".ldap.bak-{stamp}")
shutil.copy2(target, backup)
target.write_text(new_s, encoding="utf-8")

print(f"openfire_server.core: ensured OpenFire LDAP provider/properties in {kind}; backup={backup}")
print("CHANGED=1")
""".replace("__DB_PATH__", str(EMBEDDED_DB_SCRIPT)).replace("__CFG_JSON__", json.dumps(cfg))

    tmp = Path(f"/tmp/openfire-embedded-db-ldap.{os.getpid()}.py")
    tmp.write_text(code, encoding="utf-8")
    try:
        r = _run(["sudo", "python3", str(tmp)])
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass

    return "CHANGED=1" in str(r.stdout or "")


def _room_local_name(label: str) -> str:
    return "".join(
        ch if ch.isalnum() else "-"
        for ch in str(label or "").strip().lower()
    ).strip("-")


def _desired_conference_rooms(cfg: dict[str, str]) -> list[dict[str, str]]:
    fqdn = str(cfg.get("fqdn", "") or "").strip().lower()
    unit = str(cfg.get("unit", "") or "").strip().lower()
    if not unit and fqdn:
        unit = fqdn.split(".", 1)[0].strip()
    if not unit:
        raise RuntimeError("openfire_server.core: cannot derive conference rooms without fqdn/unit")

    policy_id = str(
        cfg.get("policy_id", "")
        or os.environ.get("default_policy_id", "")
        or os.environ.get("DEFAULT_POLICY_ID", "")
        or ""
    ).strip()

    if not policy_id:
        try:
            from takctl.config import load_config
            policy_id = str(load_config().get("default_policy_id", "") or "").strip()
        except Exception:
            policy_id = ""

    if not policy_id:
        policy_id = "fro"

    ctx = {
        "unit": unit,
        "node_unit": unit,
        "organization": unit,
        "cert_organization": unit,
        "policy_id": policy_id,
    }

    labels: list[str] = []
    try:
        from takctl.onboarding.channels import derive_channel_sets
        sets = derive_channel_sets(ctx)
        labels = [
            str(x).strip()
            for x in (sets.get("available") or sets.get("default") or [])
            if str(x or "").strip()
        ]
    except Exception:
        labels = []

    if not labels:
        policy = Policy(policy_id=policy_id)
        topo = derive_voice_topology(policy.cfg, {"unit": unit, "policy_id": policy.policy_id})
        labels = [str(x).strip() for x in (topo.get("channels") or []) if str(x or "").strip()]

    if not labels:
        raise RuntimeError(f"openfire_server.core: policy produced no conference rooms for unit={unit} policy={policy_id}")

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for label in labels:
        local = _room_local_name(label)
        if not local or local in seen:
            continue
        if len(local) > 50:
            raise RuntimeError(f"openfire_server.core: OpenFire MUC room name exceeds 50 chars: {local}")
        seen.add(local)
        out.append({"local": local, "natural": label})
    return out


def _ensure_embedded_db_muc_rooms(cfg: dict[str, str]) -> bool:
    """Seed OpenFire persistent MUC rooms from harmonized TAKS channels."""
    rooms = _desired_conference_rooms(cfg)

    code = r"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import re
import shutil
import time

db = Path("__DB_PATH__")
log = db.with_name("openfire.log")
rooms = __ROOMS_JSON__

def sql_quote(v: str) -> str:
    return "'" + str(v).replace("'", "''") + "'"

def sql_unquote(v: str) -> str:
    return str(v).replace("''", "'")

def insert_before_log_footer(text: str, block: str) -> str:
    footers = list(re.finditer(r"^\s*SET FILES LOG SIZE .*$", text, flags=re.M))
    if footers:
        pos = footers[-1].start()
        return text[:pos].rstrip() + "\n" + block + text[pos:]
    return text.rstrip() + "\n" + block

def room_insert(service_id: int, room_id: int, room: dict[str, str], now_ms: str) -> str:
    local = str(room.get("local") or "").strip()
    natural = str(room.get("natural") or local).strip() or local
    qlocal = sql_quote(local)
    qnatural = sql_quote(natural)
    desc = sql_quote("TAKS voice/chat channel " + natural)
    return (
        "INSERT INTO OFMUCROOM VALUES("
        f"{service_id},{room_id},'{now_ms}','{now_ms}',"
        f"{qlocal},{qnatural},{desc},"
        "'0',NULL,"
        "1,0,1,0,0,1,NULL,1,1,0,0,NULL,7,0,1,1,0,0,NULL,0,NULL"
        ")"
    )

if not db.exists():
    print(f"openfire_server.core: embedded DB script not present yet: {db}")
    print("CHANGED=0")
    raise SystemExit(0)

script_text = db.read_text(encoding="utf-8", errors="replace")
log_text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""

script_has_schema = re.search(r"CREATE\s+TABLE\s+(?:PUBLIC\.)?OFMUCROOM\b", script_text, re.I) is not None
log_has_schema = re.search(r"CREATE\s+TABLE\s+(?:PUBLIC\.)?OFMUCROOM\b", log_text, re.I) is not None

if script_has_schema:
    target = db
    s = script_text
    kind = "script"
elif log_has_schema:
    target = log
    s = log_text
    kind = "log"
else:
    print("openfire_server.core: OpenFire ofMucRoom schema not present yet; deferring room seed")
    print("CHANGED=0")
    raise SystemExit(0)

svc = re.search(r"INSERT INTO OFMUCSERVICE VALUES\((\d+),'conference'(?:,|\))", s)
if not svc:
    svc_id_row = re.search(r"INSERT INTO OFID VALUES\(26,(\d+)\)", s)
    service_id = int(svc_id_row.group(1)) if svc_id_row else 1
    existing_service_ids = [int(m.group(1)) for m in re.finditer(r"INSERT INTO OFMUCSERVICE VALUES\((\d+),", s)]
    if existing_service_ids:
        service_id = max(service_id, max(existing_service_ids) + 1)
    svc_line = f"INSERT INTO OFMUCSERVICE VALUES({service_id},'conference','Public Chatrooms',0)\n"
    if svc_id_row:
        s = re.sub(r"INSERT INTO OFID VALUES\(26,\d+\)", f"INSERT INTO OFID VALUES(26,{service_id + 1})", s, count=1)
    else:
        s = s.rstrip() + f"\nINSERT INTO OFID VALUES(26,{service_id + 1})\n"
    service_rows = list(re.finditer(r"INSERT INTO OFMUCSERVICE VALUES\(.*?\)\n?", s))
    if service_rows:
        pos = service_rows[-1].end()
        s = s[:pos] + svc_line + s[pos:]
    else:
        s = s.rstrip() + "\n" + svc_line
else:
    service_id = int(svc.group(1))

desired = {str(room.get("local") or "").strip() for room in rooms if str(room.get("local") or "").strip()}

existing: set[str] = set()
max_room_id = 0
for m in re.finditer(r"INSERT INTO OFMUCROOM VALUES\((\d+),(\d+),'[^']*','[^']*','((?:''|[^'])*)',", s):
    sid = int(m.group(1))
    rid = int(m.group(2))
    if rid > max_room_id:
        max_room_id = rid
    if sid == service_id:
        existing.add(sql_unquote(m.group(3)).lower())

removed_unknown = False
if "org-unknown-unit" in existing and "org-unknown-unit" not in desired:
    kept = []
    for line in s.splitlines():
        if "INSERT INTO OFMUCROOM VALUES(" in line and "'org-unknown-unit'" in line:
            removed_unknown = True
            continue
        kept.append(line)
    s = "\n".join(kept) + "\n"
    existing.discard("org-unknown-unit")

missing = [room for room in rooms if str(room.get("local") or "").strip() not in existing]
if not missing and not removed_unknown:
    print(f"openfire_server.core: OpenFire MUC rooms already seeded ({len(rooms)} desired)")
    print("CHANGED=0")
    raise SystemExit(0)

ofid = re.search(r"INSERT INTO OFID VALUES\(27,(\d+)\)", s)
next_room_id = max_room_id + 1
if ofid:
    next_room_id = max(next_room_id, int(ofid.group(1)))
next_room_id = max(next_room_id, 1)

now_ms = str(int(time.time() * 1000))
room_lines = []
for room in missing:
    room_lines.append(room_insert(service_id, next_room_id, room, now_ms))
    next_room_id += 1

if ofid:
    s = re.sub(r"INSERT INTO OFID VALUES\(27,\d+\)", f"INSERT INTO OFID VALUES(27,{next_room_id})", s, count=1)
else:
    s = s.rstrip() + f"\nINSERT INTO OFID VALUES(27,{next_room_id})\n"

service_rows = list(re.finditer(r"INSERT INTO OFMUCSERVICE VALUES\(.*?\)\n?", s))
if not service_rows:
    print("openfire_server.core: could not find OFMUCSERVICE insertion point; leaving rooms unchanged")
    print("CHANGED=0")
    raise SystemExit(0)

insert_pos = service_rows[-1].end()
insert_text = "".join(line + "\n" for line in room_lines)
if kind == "log" and insert_text:
    insert_text = insert_text + "COMMIT\n"
new_s = s[:insert_pos] + insert_text + s[insert_pos:]

if kind == "log":
    new_s = insert_before_log_footer("", new_s) if not new_s.strip() else new_s

stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
backup = target.with_name(target.name + f".mucrooms.bak-{stamp}")
shutil.copy2(target, backup)
target.write_text(new_s, encoding="utf-8")

print(f"openfire_server.core: seeded {len(missing)} OpenFire MUC rooms in {kind}; removed_unknown={str(removed_unknown).lower()} backup={backup}")
print("CHANGED=1")
""".replace("__DB_PATH__", str(EMBEDDED_DB_SCRIPT)).replace("__ROOMS_JSON__", json.dumps(rooms))

    tmp = Path(f"/tmp/openfire-muc-rooms.{os.getpid()}.py")
    tmp.write_text(code, encoding="utf-8")
    try:
        r = _run(["sudo", "python3", str(tmp)])
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass

    return "CHANGED=1" in str(r.stdout or "")


def _ensure_martine_openfire_db_acl() -> None:
    for cmd in (
        ["sudo", "setfacl", "-m", "u:tak:x", "/var/lib/openfire"],
        ["sudo", "setfacl", "-m", "u:tak:rx", "/var/lib/openfire/embedded-db"],
        ["sudo", "setfacl", "-m", "u:tak:r", "/var/lib/openfire/embedded-db/openfire.script"],
        ["sudo", "setfacl", "-m", "u:tak:r", "/var/lib/openfire/embedded-db/openfire.log"],
    ):
        _run(cmd, check=False)


def _sync_xmpp_bookmark_jobs() -> None:
    py = Path("/opt/tak/tools/martine/.venv/bin/python")
    if not py.exists():
        print("openfire_server.core: martine venv not present; skipping XMPP bookmark sync")
        return

    env_path = "/opt/tak/tools/takctl:" + os.environ.get("PYTHONPATH", "")
    for subcmd in ("clean-jobs", "backfill-jobs"):
        _run(
            [
                "sudo",
                "env",
                f"PYTHONPATH={env_path}",
                str(py),
                "-m",
                "takctl.onboarding.openfire_rooms",
                subcmd,
            ],
            check=False,
        )

def _autosetup_xml(cfg: dict[str, str]) -> str:
    fqdn = str(cfg["fqdn"] or "").strip()
    admin_password = str(cfg["admin_password"] or "")
    admin_email = str(cfg["admin_email"] or "").strip()
    admin_interface = str(cfg["admin_interface"] or "127.0.0.1").strip() or "127.0.0.1"

    enc_key = hashlib.sha256(f"{fqdn}|{admin_password}".encode("utf-8")).hexdigest()[:32]

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<jive>
  <adminConsole>
    <port>9090</port>
    <securePort>9091</securePort>
    <interface>{escape(admin_interface)}</interface>
  </adminConsole>

  <locale>en</locale>

  <connectionProvider>
    <className>org.jivesoftware.database.EmbeddedConnectionProvider</className>
  </connectionProvider>

  <autosetup>
    <run>true</run>
    <locale>en</locale>

    <xmpp>
      <domain>{escape(fqdn)}</domain>
      <fqdn>{escape(fqdn)}</fqdn>
      <auth>
        <anonymous>false</anonymous>
      </auth>
      <client>
        <cert>
          <policy>{escape(str(cfg.get("xmpp_client_cert_policy") or "wanted"))}</policy>
        </cert>
      </client>
      <socket>
        <ssl>
          <active>true</active>
        </ssl>
      </socket>
    </xmpp>

    <encryption>
      <algorithm>AES</algorithm>
      <key>{escape(enc_key)}</key>
    </encryption>

    <database>
      <mode>embedded</mode>
    </database>

    <admin>
      <email>{escape(admin_email)}</email>
      <password>{escape(admin_password)}</password>
    </admin>

    <authprovider>
      <mode>default</mode>
    </authprovider>
  </autosetup>
</jive>
"""


def _runtime_xml(cfg: dict[str, str]) -> str:
    fqdn = str(cfg.get("fqdn", "") or "").strip()
    admin_interface = str(cfg.get("admin_interface", "") or "127.0.0.1").strip() or "127.0.0.1"
    cert_policy = str(cfg.get("xmpp_client_cert_policy", "") or "wanted").strip().lower()

    cert_block = ""
    if cert_policy and cert_policy != "disabled":
        cert_block = f"""
    <client>
      <cert>
        <policy>{escape(cert_policy)}</policy>
      </cert>
    </client>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>

<jive>
  <adminConsole>
    <port>9090</port>
    <securePort>9091</securePort>
    <interface>{escape(admin_interface)}</interface>
  </adminConsole>
  <locale>en</locale>
  <connectionProvider>
    <className>org.jivesoftware.database.EmbeddedConnectionProvider</className>
  </connectionProvider>
  <setup>true</setup>
  <fqdn>{escape(fqdn)}</fqdn>
  <xmpp>{cert_block}
  </xmpp>
</jive>
"""


def _ensure_runtime_xml_policy(cfg: dict[str, str]) -> bool:
    """Normalize OpenFire runtime XML after autosetup.

    The working TAKS OpenFire shape has setup=true plus an XMPP client
    certificate policy of wanted. This requests client certs at TLS time
    while still allowing password SASL. It does not by itself enable SASL
    EXTERNAL.
    """
    desired = _runtime_xml(cfg)

    try:
        current = CONFIG.read_text(encoding="utf-8")
    except Exception:
        current = ""

    if current.strip() == desired.strip():
        return False

    tmp = Path(f"/tmp/openfire.xml.runtime.{os.getpid()}")
    tmp.write_text(desired, encoding="utf-8")

    try:
        _run(["sudo", "install", "-d", "-m", "0755", "/etc/openfire"])
        _run([
            "sudo", "install",
            "-o", "openfire",
            "-g", "openfire",
            "-m", "0640",
            str(tmp),
            str(CONFIG),
        ])
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass

    print(
        "openfire_server.core: normalized runtime openfire.xml "
        f"(xmpp_client_cert_policy={cfg.get('xmpp_client_cert_policy')})"
    )
    return True


def _materialize_autosetup(cfg: dict[str, str]) -> None:
    xml = _autosetup_xml(cfg)

    tmp = Path(f"/tmp/openfire.xml.taks.{os.getpid()}")
    tmp.write_text(xml, encoding="utf-8")

    try:
        _run(["sudo", "install", "-d", "-m", "0755", "/etc/openfire"])
        _run([
            "sudo", "install",
            "-o", "openfire",
            "-g", "openfire",
            "-m", "0640",
            str(tmp),
            str(CONFIG),
        ])
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


@dataclass(frozen=True)
class _Action:
    ID: str = "openfire_server.core"

    def inspect(self, ctx: Context) -> int:
        cfg = _ensure_secret_defaults(_cfg(ctx))
        installed = _pkg_version()
        enabled = _systemctl_state("is-enabled")
        active = _systemctl_state("is-active")

        print("openfire_server.core")
        print(f"  openfire_enabled:   {cfg['enabled']}")
        print(f"  desired_version:    {cfg['version']}")
        print(f"  installed_version:  {installed or '(not installed)'}")
        print(f"  service_enabled:    {enabled or '(unknown)'}")
        print(f"  service_active:     {active or '(unknown)'}")
        print(f"  fqdn:               {cfg['fqdn'] or '(missing)'}")
        print(f"  admin_email:        {cfg['admin_email'] or '(missing)'}")
        print(f"  admin_password_set: {'yes' if cfg['admin_password'] else 'no'}")
        print(f"  setup_complete:     {str(_setup_complete()).lower()}")
        print(f"  deb_url:            {cfg['deb_url']}")
        print(f"  secret_file:        {SECRET_FILE}")
        return 0

    def apply(self, ctx: Context) -> int:
        cfg = _ensure_secret_defaults(_cfg(ctx))

        if cfg["enabled"] != "true":
            print("applied: openfire_server.core skipped (openfire_enabled != true)")
            return 0

        if not cfg["fqdn"]:
            raise RuntimeError("openfire_server.core: missing fqdn")
        if not cfg["admin_password"]:
            generated = _generate_openfire_admin_password_for_install()
            _persist_openfire_admin_password_for_install(generated)
            cfg["admin_password"] = generated
            print(f"openfire_server.core: generated and stored admin password in {SECRET_FILE}")

        version = cfg["version"]
        deb_url = cfg["deb_url"]
        deb_name = f"openfire_{version}_all.deb"
        deb_path = CACHE_DIR / deb_name

        _run(["sudo", "apt-get", "update"])
        _run([
            "sudo", "apt-get", "install", "-y",
            "ca-certificates",
            "curl",
            "acl",
        ])

        java_ok = subprocess.run(
            ["bash", "-lc", "command -v java >/dev/null 2>&1"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0

        if java_ok:
            print("openfire_server.core: java already present")
        else:
            print("openfire_server.core: java missing, installing default-jre-headless")
            _run(["sudo", "apt-get", "install", "-y", "default-jre-headless"])

        _run(["sudo", "install", "-d", "-m", "0755", str(CACHE_DIR)])

        installed = _pkg_version()
        if installed != version:
            print(f"openfire_server.core: downloading {deb_url}")
            _run(["sudo", "curl", "-fL", "-o", str(deb_path), deb_url])

            p = _run(["sudo", "dpkg", "-i", str(deb_path)], check=False)
            if p.returncode != 0:
                _run(["sudo", "apt-get", "install", "-f", "-y"])
        else:
            print(f"openfire_server.core: package already at desired version {version}")

        setup_was_complete = _setup_complete()

        _run(["sudo", "systemctl", "stop", SERVICE], check=False)

        if setup_was_complete:
            print("openfire_server.core: existing setup already complete, leaving openfire.xml as-is")
        else:
            print("openfire_server.core: writing headless autosetup openfire.xml")
            _materialize_autosetup(cfg)

        _run(["sudo", "systemctl", "daemon-reload"], check=False)
        _run(["sudo", "systemctl", "enable", SERVICE])

        if setup_was_complete:
            _ensure_runtime_xml_policy(cfg)
            _ensure_embedded_db_auth_provider_consistency(cfg)
            _ensure_embedded_db_muc_rooms(cfg)
            _ensure_martine_openfire_db_acl()
            _sync_xmpp_bookmark_jobs()
            _run(["sudo", "systemctl", "start", SERVICE])
        else:
            _run(["sudo", "systemctl", "restart", SERVICE])
            if _wait_for_setup_complete():
                _run(["sudo", "systemctl", "stop", SERVICE], check=False)
                _ensure_runtime_xml_policy(cfg)
                _ensure_embedded_db_auth_provider_consistency(cfg)
                _ensure_embedded_db_muc_rooms(cfg)
                _ensure_martine_openfire_db_acl()
                _sync_xmpp_bookmark_jobs()
                _run(["sudo", "systemctl", "start", SERVICE])
            else:
                print("openfire_server.core: setup did not report complete; skipping embedded DB provider repair")

        final_version = _pkg_version()
        final_active = _systemctl_state("is-active")
        print(
            f"applied: openfire_server.core "
            f"(version={final_version or 'unknown'} active={final_active or 'unknown'} setup_complete={str(_setup_complete()).lower()})"
        )
        return 0


ACTION = _Action()
