from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Sequence

from .models import UserRecord


class UserDirectory(ABC):
    """
    Read-only identity observation layer.
    MUST NOT own or mutate identity truth.
    """

    @abstractmethod
    def list_users(self) -> Sequence[UserRecord]:
        raise NotImplementedError

    @abstractmethod
    def get_user(self, username: str) -> Optional[UserRecord]:
        raise NotImplementedError

    def user_exists(self, username: str) -> bool:
        return self.get_user(username) is not None

