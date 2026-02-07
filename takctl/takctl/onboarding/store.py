from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Sequence

from .models import OnboardingRecord


class OnboardingStore(ABC):
    """
    takctl-owned state store. This is NOT Marti state.
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

