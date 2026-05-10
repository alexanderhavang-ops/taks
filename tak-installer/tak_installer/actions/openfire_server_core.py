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
    env = dict(ctx.env or {})
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

    return {
        "enabled": "true" if enabled else "false",
        "version": version,
        "deb_url": f"https://download.igniterealtime.org/openfire/openfire_{version}_all.deb",
        "admin_password": admin_password,
        "admin_email": admin_email,
        "admin_interface": admin_interface,
        "fqdn": fqdn,
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


def _ensure_embedded_db_auth_provider_consistency() -> bool:
    """
    Repair the OpenFire embedded DB provider rows after autosetup.

    TAKS uses OpenFire with LDAP-backed users. OpenFire can end up in a split
    provider state where users come from LDAP but auth is still the local
    DefaultAuthProvider. In that state TakChat clients can find LDAP users, but
    SCRAM/PLAIN auth fails against the empty local OFUSER table.

    This helper is intentionally narrow:
      - only acts on the embedded HSQLDB script;
      - only changes auth provider when the user provider is already LDAP;
      - backs up the script before changing it;
      - is called while OpenFire is stopped.
    """
    code = r"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil

db = Path("__DB_PATH__")
old_auth = "INSERT INTO OFPROPERTY VALUES('provider.auth.className','org.jivesoftware.openfire.auth.DefaultAuthProvider',0,NULL)"
new_auth = "INSERT INTO OFPROPERTY VALUES('provider.auth.className','org.jivesoftware.openfire.ldap.LdapAuthProvider',0,NULL)"
ldap_user = "INSERT INTO OFPROPERTY VALUES('provider.user.className','org.jivesoftware.openfire.ldap.LdapUserProvider',0,NULL)"

if not db.exists():
    print(f"openfire_server.core: embedded DB script not present yet: {db}")
    print("CHANGED=0")
    raise SystemExit(0)

s = db.read_text(encoding="utf-8")

if ldap_user not in s:
    print("openfire_server.core: OpenFire user provider is not LDAP; leaving auth provider unchanged")
    print("CHANGED=0")
    raise SystemExit(0)

if new_auth in s:
    print("openfire_server.core: OpenFire auth provider already LDAP")
    print("CHANGED=0")
    raise SystemExit(0)

if old_auth not in s:
    print("openfire_server.core: could not find DefaultAuthProvider row; leaving auth provider unchanged")
    print("CHANGED=0")
    raise SystemExit(0)

stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
backup = db.with_name(db.name + f".bak-{stamp}")
shutil.copy2(db, backup)

db.write_text(s.replace(old_auth, new_auth, 1), encoding="utf-8")

print(f"openfire_server.core: switched OpenFire auth provider to LDAP; backup={backup}")
print("CHANGED=1")
""".replace("__DB_PATH__", str(EMBEDDED_DB_SCRIPT))

    tmp = Path(f"/tmp/openfire-embedded-db-provider.{os.getpid()}.py")
    tmp.write_text(code, encoding="utf-8")
    try:
        r = _run(["sudo", "python3", str(tmp)])
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass

    return "CHANGED=1" in str(r.stdout or "")


def _desired_conference_rooms(cfg: dict[str, str]) -> list[str]:
    fqdn = str(cfg.get("fqdn", "") or "").strip().lower()
    unit = fqdn.split(".", 1)[0].strip() if fqdn else ""
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
        policy_id = "hemvarnet"

    policy = Policy(policy_id=policy_id)
    topo = derive_voice_topology(policy.cfg, {"unit": unit, "policy_id": policy.policy_id})
    rooms = [str(x).strip() for x in (topo.get("channels") or []) if str(x or "").strip()]
    if not rooms:
        raise RuntimeError(f"openfire_server.core: voice topology produced no conference rooms for unit={unit}")

    too_long = [x for x in rooms if len(x) > 50]
    if too_long:
        raise RuntimeError(
            "openfire_server.core: OpenFire MUC room name exceeds 50 chars: "
            + ", ".join(too_long)
        )

    out: list[str] = []
    seen: set[str] = set()
    for room in rooms:
        if room in seen:
            continue
        seen.add(room)
        out.append(room)
    return out


def _ensure_embedded_db_muc_rooms(cfg: dict[str, str]) -> bool:
    """
    Seed OpenFire persistent MUC rooms from the same voice topology that Mumble uses.

    The room set is global/discoverable under the built-in conference service. This
    does not attempt per-user bookmarks or rosters; TakChat should at least be able
    to browse/join these conference rooms once OpenFire is restarted.
    """
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
rooms = __ROOMS_JSON__

def sql_quote(v: str) -> str:
    return "'" + str(v).replace("'", "''") + "'"

def sql_unquote(v: str) -> str:
    return str(v).replace("''", "'")

def room_insert(service_id: int, room_id: int, name: str, now_ms: str) -> str:
    qname = sql_quote(name)
    desc = sql_quote("TAKS voice/chat channel " + name)
    # ofMucRoom column order as in OpenFire 5.x schema:
    # serviceID, roomID, creationDate, modificationDate, name, naturalName,
    # description, lockedDate, emptyDate, canChangeSubject, maxUsers,
    # publicRoom, moderated, membersOnly, canInvite, roomPassword,
    # canDiscoverJID, logEnabled, retireOnDeletion, preserveHistOnDel,
    # subject, rolesToBroadcast, useReservedNick, canChangeNick,
    # canRegister, allowpm, fmucEnabled, fmucOutboundNode, fmucOutboundMode,
    # fmucInboundNodes
    return (
        "INSERT INTO OFMUCROOM VALUES("
        f"{service_id},{room_id},'{now_ms}','{now_ms}',"
        f"{qname},{qname},{desc},"
        "'0',NULL,"
        "1,0,1,0,0,1,NULL,1,0,0,0,NULL,7,0,1,1,0,0,NULL,0,NULL"
        ")"
    )

if not db.exists():
    print(f"openfire_server.core: embedded DB script not present yet: {db}")
    print("CHANGED=0")
    raise SystemExit(0)

s = db.read_text(encoding="utf-8")

svc = re.search(r"INSERT INTO OFMUCSERVICE VALUES\((\d+),'conference'(?:,|\))", s)
if not svc:
    print("openfire_server.core: OpenFire conference MUC service is missing; leaving rooms unchanged")
    print("CHANGED=0")
    raise SystemExit(0)

service_id = int(svc.group(1))

existing: set[str] = set()
max_room_id = 0
for m in re.finditer(r"INSERT INTO OFMUCROOM VALUES\((\d+),(\d+),'[^']*','[^']*','((?:''|[^'])*)',", s):
    sid = int(m.group(1))
    rid = int(m.group(2))
    if rid > max_room_id:
        max_room_id = rid
    if sid == service_id:
        existing.add(sql_unquote(m.group(3)))

missing = [room for room in rooms if room not in existing]
if not missing:
    print(f"openfire_server.core: OpenFire MUC rooms already seeded ({len(rooms)} desired)")
    print("CHANGED=0")
    raise SystemExit(0)

ofid = re.search(r"INSERT INTO OFID VALUES\(27,(\d+)\)", s)
next_room_id = max_room_id + 1
if ofid:
    next_room_id = max(next_room_id, int(ofid.group(1)))
next_room_id = max(next_room_id, 1)

now_ms = str(int(time.time() * 1000))
lines: list[str] = []
for room in missing:
    lines.append(room_insert(service_id, next_room_id, room, now_ms))
    next_room_id += 1

if ofid:
    s = re.sub(r"INSERT INTO OFID VALUES\(27,\d+\)", f"INSERT INTO OFID VALUES(27,{next_room_id})", s, count=1)
else:
    last_ofid = list(re.finditer(r"INSERT INTO OFID VALUES\(\d+,\d+\)\n?", s))
    if last_ofid:
        pos = last_ofid[-1].end()
        s = s[:pos] + f"INSERT INTO OFID VALUES(27,{next_room_id})\n" + s[pos:]
    else:
        print("openfire_server.core: could not find OFID rows; leaving rooms unchanged")
        print("CHANGED=0")
        raise SystemExit(0)

service_rows = list(re.finditer(r"INSERT INTO OFMUCSERVICE VALUES\(.*?\)\n?", s))
if not service_rows:
    print("openfire_server.core: could not find OFMUCSERVICE insertion point; leaving rooms unchanged")
    print("CHANGED=0")
    raise SystemExit(0)

insert_pos = service_rows[-1].end()
insert_text = "".join(line + "\n" for line in lines)
new_s = s[:insert_pos] + insert_text + s[insert_pos:]

stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
backup = db.with_name(db.name + f".mucrooms.bak-{stamp}")
shutil.copy2(db, backup)
db.write_text(new_s, encoding="utf-8")

print(f"openfire_server.core: seeded {len(missing)} OpenFire MUC rooms under conference; backup={backup}")
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
            _ensure_embedded_db_auth_provider_consistency()
            _ensure_embedded_db_muc_rooms(cfg)
            _run(["sudo", "systemctl", "start", SERVICE])
        else:
            _run(["sudo", "systemctl", "restart", SERVICE])
            if _wait_for_setup_complete():
                _run(["sudo", "systemctl", "stop", SERVICE], check=False)
                _ensure_embedded_db_auth_provider_consistency()
                _ensure_embedded_db_muc_rooms(cfg)
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
