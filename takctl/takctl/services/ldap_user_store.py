from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from takctl.config import load_config, load_secrets
from takctl.onboarding.models import UserRecord


class LdapUserStoreError(RuntimeError):
    pass


_STORE_ALIASES = {
    "": "userauthfile",
    "file": "userauthfile",
    "xml": "userauthfile",
    "marti_xml": "userauthfile",
    "userauthfile": "userauthfile",
    "user_auth_file": "userauthfile",
    "userauthenticationfile": "userauthfile",
    "ldap": "ldap",
    "ldap_local": "ldap",
    "openldap": "ldap",
}


def normalize_backing_user_store(value: str | None) -> str:
    key = str(value or "").strip().lower().replace("-", "_")
    if key not in _STORE_ALIASES:
        raise ValueError("backing_user_store must be one of: ldap, userauthfile")
    return _STORE_ALIASES[key]


def selected_backing_user_store(override: str | None = None) -> str:
    if override is not None and str(override).strip():
        return normalize_backing_user_store(override)
    cfg = load_config()
    return normalize_backing_user_store(str(cfg.get("backing_user_store", "userauthfile") or "userauthfile"))


def _cfg_get(cfg: Any, key: str, default: str = "") -> str:
    try:
        v = cfg.get(key, default)
    except Exception:
        v = default
    return str(v if v is not None else "").strip()


def _sec_get(sec: Any, key: str, default: str = "") -> str:
    try:
        v = sec.get(key, default)
    except Exception:
        v = default
    return str(v if v is not None else "").strip()


def _read_kv_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and ((v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'")):
            v = v[1:-1]
        if k:
            out[k] = v
    return out


def _merge_nonempty(dst: dict[str, str], src: dict[str, str]) -> None:
    for k, v in src.items():
        if str(v or "").strip():
            dst[k] = v


def _runtime_fallbacks() -> tuple[dict[str, str], dict[str, str]]:
    cfg: dict[str, str] = {}
    sec: dict[str, str] = {}
    for d in (
        Path("/opt/tak/tools/takctl/conf.d"),
        Path("/etc/taks-bootstrap.d/config.d"),
    ):
        if d.exists():
            for f in sorted(d.glob("*.conf")):
                _merge_nonempty(cfg, _read_kv_file(f))
    for p in (
        Path("/etc/taks/ldap-secrets.conf"),
    ):
        _merge_nonempty(sec, _read_kv_file(p))
    for d in (
        Path("/opt/tak/tools/takctl/secrets.d"),
        Path("/etc/taks-bootstrap.d/secrets.d"),
    ):
        if d.exists():
            for f in sorted(d.glob("*.conf")):
                _merge_nonempty(sec, _read_kv_file(f))
    return cfg, sec


def _derive_base_dn_from_fqdn() -> str:
    for p in (
        Path("/opt/tak/tools/takctl/conf.d/node.conf"),
        Path("/etc/taks-bootstrap.d/config.d/node.conf"),
    ):
        data = _read_kv_file(p)
        fqdn = (data.get("node_fqdn") or data.get("fqdn") or "").strip()
        if fqdn and "." in fqdn:
            parts = [x.strip().lower() for x in fqdn.split(".") if x.strip()]
            if len(parts) >= 2:
                return ",".join(f"dc={x}" for x in parts)
    return "dc=taks,dc=local"


@dataclass(frozen=True)
class LdapConfig:
    uri: str
    base_dn: str
    people_ou: str
    groups_ou: str
    services_ou: str
    bind_dn: str
    bind_password: str
    write_dn: str
    write_password: str
    user_rdn_attr: str = "uid"
    group_name_attr: str = "cn"
    group_member_attr: str = "member"
    group_object_class: str = "groupOfNames"
    group_name_extractor_regex: str = r"^cn=([^,]+),.*$"
    manage_local: bool = True

    @property
    def people_base_dn(self) -> str:
        return f"ou={self.people_ou},{self.base_dn}"

    @property
    def groups_base_dn(self) -> str:
        return f"ou={self.groups_ou},{self.base_dn}"

    @property
    def services_base_dn(self) -> str:
        return f"ou={self.services_ou},{self.base_dn}"

    def user_dn(self, username: str) -> str:
        return f"{self.user_rdn_attr}={escape_dn_value(username)},{self.people_base_dn}"

    def group_dn(self, group: str) -> str:
        return f"{self.group_name_attr}={escape_dn_value(group)},{self.groups_base_dn}"


def load_ldap_config() -> LdapConfig:
    cfg = load_config()
    sec = load_secrets()
    cfg_fb, sec_fb = _runtime_fallbacks()

    def c(key: str, default: str = "") -> str:
        return _cfg_get(cfg, key, cfg_fb.get(key, default)) or cfg_fb.get(key, default)

    def s(key: str, default: str = "") -> str:
        return _sec_get(sec, key, sec_fb.get(key, default)) or sec_fb.get(key, default)

    base_dn = c("ldap_base_dn", "") or _derive_base_dn_from_fqdn()
    people_ou = c("ldap_people_ou", "people") or "people"
    groups_ou = c("ldap_groups_ou", "groups") or "groups"
    services_ou = c("ldap_services_ou", "services") or "services"

    bind_dn = c("ldap_service_account_dn", "")
    if not bind_dn:
        bind_dn = c("ldap_bind_dn", "")
    if not bind_dn:
        bind_dn = f"cn=taksvc,ou={services_ou},{base_dn}"

    bind_password = s("ldap_service_account_password", "")
    if not bind_password:
        bind_password = s("ldap_bind_password", "")

    write_dn = c("ldap_admin_dn", f"cn=admin,{base_dn}")
    write_password = s("ldap_admin_password", "")
    if not write_password:
        write_dn = bind_dn
        write_password = bind_password

    manage_raw = c("ldap_manage_local", "true").strip().lower()
    manage_local = manage_raw in ("1", "true", "yes", "y", "on")

    return LdapConfig(
        uri=c("ldap_uri", "ldap://127.0.0.1:389") or "ldap://127.0.0.1:389",
        base_dn=base_dn,
        people_ou=people_ou,
        groups_ou=groups_ou,
        services_ou=services_ou,
        bind_dn=bind_dn,
        bind_password=bind_password,
        write_dn=write_dn,
        write_password=write_password,
        user_rdn_attr=c("ldap_user_rdn_attr", "uid") or "uid",
        group_name_attr=c("ldap_group_name_attr", "cn") or "cn",
        group_member_attr=c("ldap_group_member_attr", "member") or "member",
        group_object_class=c("ldap_group_object_class", "groupOfNames") or "groupOfNames",
        group_name_extractor_regex=c("ldap_group_name_extractor_regex", r"^cn=([^,]+),.*$") or r"^cn=([^,]+),.*$",
        manage_local=manage_local,
    )


_DN_ESCAPE_RE = re.compile(r'([,+"\\<>;=])')


def escape_dn_value(value: str) -> str:
    s = str(value or "").strip()
    s = _DN_ESCAPE_RE.sub(r"\\\1", s)
    if s.startswith(" "):
        s = "\\20" + s[1:]
    if s.endswith(" "):
        s = s[:-1] + "\\20"
    if s.startswith("#"):
        s = "\\#" + s[1:]
    return s


def escape_filter_value(value: str) -> str:
    out = []
    for ch in str(value or ""):
        if ch == "*":
            out.append(r"\2a")
        elif ch == "(":
            out.append(r"\28")
        elif ch == ")":
            out.append(r"\29")
        elif ch == "\\":
            out.append(r"\5c")
        elif ch == "\x00":
            out.append(r"\00")
        else:
            out.append(ch)
    return "".join(out)


def _normalize_groups(*chunks: Iterable[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        for raw in (chunk or []):
            g = str(raw or "").strip()
            if not g or g in seen:
                continue
            seen.add(g)
            out.append(g)
    return out


def _parse_dns(text: str) -> list[str]:
    dns: list[str] = []
    cur: Optional[str] = None
    for raw in str(text or "").splitlines():
        if raw.startswith("dn: "):
            if cur:
                dns.append(cur)
            cur = raw[4:].strip()
        elif raw.startswith(" ") and cur:
            cur += raw[1:].strip()
    if cur:
        dns.append(cur)
    return dns


class LdapUserStore:
    name = "ldap"

    def __init__(self, config: LdapConfig | None = None):
        self.config = config or load_ldap_config()

    def _require_password(self) -> None:
        if not self.config.write_dn or not self.config.write_password:
            raise LdapUserStoreError("missing LDAP write bind DN/password (ldap_admin_dn/ldap_admin_password or service fallback)")

    def _run(self, args: Sequence[str], *, input_text: str | None = None, check: bool = True) -> str:
        self._require_password()
        env = dict(os.environ)
        env.setdefault("LDAPTLS_REQCERT", "never")
        try:
            p = subprocess.run(
                list(args),
                input=input_text,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
            )
        except FileNotFoundError as e:
            raise LdapUserStoreError(f"missing LDAP utility: {e.filename}") from e
        out = str(p.stdout or "").strip()
        if check and p.returncode != 0:
            raise LdapUserStoreError(out or f"LDAP command failed: {' '.join(args)}")
        return out

    def _ldapsearch(self, base: str, ldap_filter: str, attrs: Sequence[str] = ("dn",)) -> str:
        return self._run([
            "ldapsearch",
            "-LLL",
            "-x",
            "-H",
            self.config.uri,
            "-D",
            self.config.write_dn,
            "-w",
            self.config.write_password,
            "-b",
            base,
            ldap_filter,
            *list(attrs),
        ])

    def _ldapmodify(self, ldif: str) -> str:
        return self._run([
            "ldapmodify",
            "-x",
            "-H",
            self.config.uri,
            "-D",
            self.config.write_dn,
            "-w",
            self.config.write_password,
        ], input_text=ldif)

    def _ldapadd(self, ldif: str, *, check: bool = True) -> str:
        return self._run([
            "ldapadd",
            "-x",
            "-H",
            self.config.uri,
            "-D",
            self.config.write_dn,
            "-w",
            self.config.write_password,
        ], input_text=ldif, check=check)

    def _ldapdelete(self, dn: str, *, check: bool = True) -> str:
        return self._run([
            "ldapdelete",
            "-x",
            "-H",
            self.config.uri,
            "-D",
            self.config.write_dn,
            "-w",
            self.config.write_password,
            dn,
        ], check=check)

    def _set_password(self, user_dn: str, password: str) -> None:
        if not password:
            return
        self._run([
            "ldappasswd",
            "-x",
            "-H",
            self.config.uri,
            "-D",
            self.config.write_dn,
            "-w",
            self.config.write_password,
            "-s",
            password,
            user_dn,
        ])

    def get_user(self, username: str) -> UserRecord | None:
        u = str(username or "").strip()
        if not u:
            return None
        dn = self.config.user_dn(u)
        try:
            out = self._ldapsearch(dn, "(objectClass=*)", ("dn",))
        except LdapUserStoreError:
            return None
        if not _parse_dns(out):
            return None
        return UserRecord(username=u, groups=self.groups_for_user(u))

    def list_users(self) -> Sequence[UserRecord]:
        try:
            out = self._ldapsearch(
                self.config.people_base_dn,
                f"({self.config.user_rdn_attr}=*)",
                (self.config.user_rdn_attr,),
            )
        except LdapUserStoreError:
            return []
        records: list[UserRecord] = []
        for dn in _parse_dns(out):
            username = self._username_from_dn(dn)
            if username:
                records.append(UserRecord(username=username, groups=self.groups_for_user(username)))
        records.sort(key=lambda x: x.username.lower())
        return records

    def _username_from_dn(self, dn: str) -> str:
        first = str(dn or "").split(",", 1)[0]
        prefix = self.config.user_rdn_attr + "="
        if first.lower().startswith(prefix.lower()):
            return first[len(prefix):].replace(r"\,", ",").replace(r"\+", "+").replace(r"\\", "\\")
        return ""

    def groups_for_user(self, username: str) -> list[str]:
        u = str(username or "").strip()
        if not u:
            return []
        user_dn = self.config.user_dn(u)
        filt = f"({self.config.group_member_attr}={escape_filter_value(user_dn)})"
        try:
            out = self._ldapsearch(self.config.groups_base_dn, filt, (self.config.group_name_attr,))
        except LdapUserStoreError:
            return []
        groups: list[str] = []
        regex = re.compile(self.config.group_name_extractor_regex or r"^cn=([^,]+),.*$")
        for dn in _parse_dns(out):
            m = regex.search(dn)
            if m:
                groups.append(m.group(1))
            else:
                first = dn.split(",", 1)[0]
                if "=" in first:
                    groups.append(first.split("=", 1)[1])
        return sorted({g for g in groups if g})

    def ensure_group(self, group: str, *, initial_member_dn: str | None = None) -> None:
        g = str(group or "").strip()
        if not g:
            return
        dn = self.config.group_dn(g)
        try:
            out = self._ldapsearch(dn, "(objectClass=*)", ("dn",))
            if _parse_dns(out):
                return
        except LdapUserStoreError:
            pass

        member = initial_member_dn or self.config.bind_dn
        ldif = f"""
dn: {dn}
objectClass: top
objectClass: {self.config.group_object_class}
{self.config.group_name_attr}: {g}
{self.config.group_member_attr}: {member}

"""
        self._ldapadd(ldif)

    def ensure_user(
        self,
        username: str,
        *,
        password: str | None = None,
        admin: bool | None = None,
        groups: Sequence[str] | None = None,
        in_groups: Sequence[str] | None = None,
        out_groups: Sequence[str] | None = None,
        append: bool = False,
        remove: bool = False,
        certificate_path: str | None = None,
        ctx: dict[str, Any] | None = None,
    ) -> str:
        u = str(username or "").strip()
        if not u:
            raise LdapUserStoreError("username required")

        desired_groups = _normalize_groups(groups, in_groups, out_groups)
        user_dn = self.config.user_dn(u)
        existed = self.get_user(u) is not None

        mail = ""
        try:
            mail = str((ctx or {}).get("email") or "").strip()
        except Exception:
            mail = ""

        if not existed:
            if password is None:
                raise LdapUserStoreError(f"password required when creating LDAP user: {u}")
            attrs = [
                f"dn: {user_dn}",
                "objectClass: top",
                "objectClass: person",
                "objectClass: organizationalPerson",
                "objectClass: inetOrgPerson",
                f"{self.config.user_rdn_attr}: {u}",
                f"cn: {u}",
                f"sn: {u}",
            ]
            if mail:
                attrs.append(f"mail: {mail}")
            if admin is True:
                attrs.append("employeeType: tak-admin")
            if certificate_path:
                attrs.append(f"description: TAK client certificate path: {certificate_path}")
            self._ldapadd("\n".join(attrs) + "\n\n")
        else:
            changes: list[str] = []
            if mail:
                changes.append(f"""dn: {user_dn}
changetype: modify
replace: mail
mail: {mail}

""")
            if admin is True:
                changes.append(f"""dn: {user_dn}
changetype: modify
replace: employeeType
employeeType: tak-admin

""")
            if certificate_path:
                changes.append(f"""dn: {user_dn}
changetype: modify
replace: description
description: TAK client certificate path: {certificate_path}

""")
            if changes:
                self._ldapmodify("".join(changes))

        if password:
            self._set_password(user_dn, password)

        if remove:
            current = self.groups_for_user(u)
            for g in current:
                self._remove_user_from_group(u, g)
        elif not append:
            current = self.groups_for_user(u)
            for g in current:
                if g not in desired_groups:
                    self._remove_user_from_group(u, g)

        for g in desired_groups:
            self.ensure_group(g, initial_member_dn=user_dn)
            self._add_user_to_group(u, g)

        return f"ldap {'updated' if existed else 'created'} {u}"

    def delete_user(self, username: str) -> str:
        u = str(username or "").strip()
        if not u:
            raise LdapUserStoreError("username required")
        for g in self.groups_for_user(u):
            self._remove_user_from_group(u, g)
        self._ldapdelete(self.config.user_dn(u), check=False)
        return f"ldap deleted {u}"

    def _add_user_to_group(self, username: str, group: str) -> None:
        user_dn = self.config.user_dn(username)
        group_dn = self.config.group_dn(group)
        ldif = f"""dn: {group_dn}
changetype: modify
add: {self.config.group_member_attr}
{self.config.group_member_attr}: {user_dn}

"""
        try:
            self._ldapmodify(ldif)
        except LdapUserStoreError as e:
            msg = str(e)
            if "Type or value exists" in msg or "already exists" in msg:
                return
            raise

    def _remove_user_from_group(self, username: str, group: str) -> None:
        user_dn = self.config.user_dn(username)
        group_dn = self.config.group_dn(group)
        ldif = f"""dn: {group_dn}
changetype: modify
delete: {self.config.group_member_attr}
{self.config.group_member_attr}: {user_dn}

"""
        try:
            self._ldapmodify(ldif)
        except LdapUserStoreError:
            # Removing a non-member or the last member of groupOfNames can fail; do not
            # make user deletion/update hostage to LDAP group cleanup.
            pass
