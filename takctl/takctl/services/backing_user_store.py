from __future__ import annotations

from typing import Any, Optional, Sequence

from takctl.services.ldap_user_store import (
    LdapUserStore,
    LdapUserStoreError,
    normalize_backing_user_store,
    selected_backing_user_store,
)
from takctl.services.usermgr import UserMgrError, UserMgrService


class BackingUserStoreError(RuntimeError):
    pass


class UserauthFileBackingUserStore:
    name = "userauthfile"

    def __init__(self, usermgr: UserMgrService | None = None):
        self.usermgr = usermgr or UserMgrService()

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
        try:
            return self.usermgr.user_set(
                username,
                password=password,
                admin=admin,
                groups=list(groups or []) or None,
                in_groups=list(in_groups or []) or None,
                out_groups=list(out_groups or []) or None,
                append=bool(append),
                remove=bool(remove),
                certificate_path=certificate_path,
            )
        except UserMgrError as e:
            raise BackingUserStoreError(str(e)) from e

    def delete_user(self, username: str) -> str:
        try:
            return self.usermgr.user_delete(username)
        except UserMgrError as e:
            raise BackingUserStoreError(str(e)) from e

    def preflight(self) -> None:
        try:
            self.usermgr.preflight()
        except UserMgrError as e:
            raise BackingUserStoreError(str(e)) from e


class LdapBackingUserStore:
    name = "ldap"

    def __init__(self, ldap: LdapUserStore | None = None):
        self.ldap = ldap or LdapUserStore()

    def ensure_user(self, username: str, **kwargs: Any) -> str:
        try:
            return self.ldap.ensure_user(username, **kwargs)
        except LdapUserStoreError as e:
            raise BackingUserStoreError(str(e)) from e

    def delete_user(self, username: str) -> str:
        try:
            return self.ldap.delete_user(username)
        except LdapUserStoreError as e:
            raise BackingUserStoreError(str(e)) from e

    def preflight(self) -> None:
        # LDAP write operations validate utilities/bind credentials on demand.
        return None


def build_backing_user_store(override: str | None = None):
    store = selected_backing_user_store(override)
    if store == "ldap":
        return LdapBackingUserStore()
    return UserauthFileBackingUserStore()


__all__ = [
    "BackingUserStoreError",
    "UserauthFileBackingUserStore",
    "LdapBackingUserStore",
    "build_backing_user_store",
    "normalize_backing_user_store",
    "selected_backing_user_store",
]
