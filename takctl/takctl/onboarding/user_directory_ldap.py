from __future__ import annotations

from typing import Optional, Sequence

from takctl.onboarding.models import UserRecord
from takctl.onboarding.user_directory import UserDirectory
from takctl.services.ldap_user_store import LdapUserStore


class UserDirectoryLdap(UserDirectory):
    """
    Read-only UserDirectory backed by the configured TAKS LDAP backend.

    TAKS still treats certificates as TAK client identity material; LDAP is only
    the user/group authority observed here.
    """

    def __init__(self, store: LdapUserStore | None = None):
        self.store = store or LdapUserStore()

    def list_users(self) -> Sequence[UserRecord]:
        return self.store.list_users()

    def get_user(self, username: str) -> Optional[UserRecord]:
        return self.store.get_user(username)
