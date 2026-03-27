from __future__ import annotations

from pathlib import Path

from takctl.config import load_config
from takctl.onboarding.service import OnboardingService
from takctl.onboarding.store_filejson import FileJsonOnboardingStore
from takctl.onboarding.user_directory_xml import UserDirectoryXml

DEFAULT_USERAUTH_XML = Path("/opt/tak/UserAuthenticationFile.xml")
DEFAULT_STATE_ROOT = Path("/opt/tak/takctl-state/onboarding")


def _default_external_base() -> str | None:
    cfg = load_config()
    v = str(cfg.get("onboarding_external_base", "") or "").strip()
    return v.rstrip("/") if v else None


def build_service(
    *,
    userauth_xml: Path = DEFAULT_USERAUTH_XML,
    state_root: Path = DEFAULT_STATE_ROOT,
    external_base: str | None = None,
) -> OnboardingService:
    ud = UserDirectoryXml(str(userauth_xml))
    store = FileJsonOnboardingStore(str(state_root))
    svc = OnboardingService(ud=ud, store=store)
    svc.external_base = (external_base or _default_external_base() or None)
    return svc
