from __future__ import annotations

import os
from pathlib import Path

from takctl.onboarding.service import OnboardingService
from takctl.onboarding.store_filejson import FileJsonOnboardingStore
from takctl.onboarding.user_directory_xml import UserDirectoryXml

DEFAULT_USERAUTH_XML = Path("/opt/tak/UserAuthenticationFile.xml")
DEFAULT_STATE_ROOT = Path("/opt/tak/takctl-state/onboarding")


def _default_external_base() -> str | None:
    """
    Best-effort external base for background jobs / non-request flows.

    Preferred:
      TAKS_EXTERNAL_BASE=https://node.example.com

    Optional legacy alias:
      TAKCTL_EXTERNAL_BASE=...

    Returns None if unset.
    """
    for k in ("TAKS_EXTERNAL_BASE", "TAKCTL_EXTERNAL_BASE"):
        v = (os.environ.get(k) or "").strip()
        if v:
            return v.rstrip("/")
    return None


def build_service(
    *,
    userauth_xml: Path = DEFAULT_USERAUTH_XML,
    state_root: Path = DEFAULT_STATE_ROOT,
    external_base: str | None = None,
) -> OnboardingService:
    ud = UserDirectoryXml(str(userauth_xml))
    store = FileJsonOnboardingStore(str(state_root))
    svc = OnboardingService(ud=ud, store=store)

    # Attach optional external base for background/import flows.
    # This keeps requestless code able to issue public soldier-card URLs.
    svc.external_base = (external_base or _default_external_base() or None)

    return svc
