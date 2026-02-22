from __future__ import annotations

from pathlib import Path

from takctl.onboarding.service import OnboardingService
from takctl.onboarding.store_filejson import FileJsonOnboardingStore
from takctl.onboarding.user_directory_xml import UserDirectoryXml

DEFAULT_USERAUTH_XML = Path("/opt/tak/UserAuthenticationFile.xml")
DEFAULT_STATE_ROOT = Path("/opt/tak/takctl-state/onboarding")


def build_service(
    *,
    userauth_xml: Path = DEFAULT_USERAUTH_XML,
    state_root: Path = DEFAULT_STATE_ROOT,
) -> OnboardingService:
    ud = UserDirectoryXml(str(userauth_xml))
    store = FileJsonOnboardingStore(str(state_root))
    return OnboardingService(ud=ud, store=store)
