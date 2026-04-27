from __future__ import annotations

from pathlib import Path

from takctl.config import load_config
from takctl.onboarding.service import OnboardingService
from takctl.onboarding.store_filejson import FileJsonOnboardingStore
from takctl.onboarding.user_directory_xml import UserDirectoryXml
from takctl.onboarding.user_directory_ldap import UserDirectoryLdap
from takctl.services.ldap_user_store import selected_backing_user_store

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
    backing_user_store: str | None = None,
) -> OnboardingService:
    store_name = selected_backing_user_store(backing_user_store)
    if store_name == "ldap":
        ud = UserDirectoryLdap()
    else:
        ud = UserDirectoryXml(str(userauth_xml))

    store = FileJsonOnboardingStore(str(state_root))
    svc = OnboardingService(ud=ud, store=store, backing_user_store=store_name)
    svc.external_base = (external_base or _default_external_base() or None)
    return svc
