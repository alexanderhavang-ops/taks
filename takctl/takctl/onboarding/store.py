from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Sequence

from .models import OnboardingRecord


class OnboardingStore(ABC):
    """
    Canonical TAKS-owned onboarding store contract.

    This store owns:
      - per-user onboarding state
      - TAKS identity overlay
      - soldier-card token state

    No legacy/stale interface beyond what current code actually uses.
    """

    @abstractmethod
    def list_records(self) -> Sequence[OnboardingRecord]:
        raise NotImplementedError

    @abstractmethod
    def get_record(self, username: str) -> Optional[OnboardingRecord]:
        raise NotImplementedError

    @abstractmethod
    def upsert_record(self, record: OnboardingRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_identity(self, username: str) -> Optional[Any]:
        raise NotImplementedError

    @abstractmethod
    def upsert_identity(
        self,
        *,
        username: str,
        origin: str,
        ctx: Dict[str, Any],
        identity: Dict[str, Any],
        password: Optional[str],
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    def create_card_token(
        self,
        *,
        username: str,
        ttl_sec: int,
        reveal_password: bool,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    def upsert_card_token(
        self,
        *,
        username: str,
        ttl_sec: int,
        reveal_password: bool,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    def get_card_token(self, token: str) -> Optional[Any]:
        raise NotImplementedError
