from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from takctl.onboarding.user_directory_xml import UserDirectoryXml
from takctl.onboarding.store_filejson import FileJsonOnboardingStore
from takctl.onboarding.service import OnboardingService


def cmd_onboarding_list(
    userauth_xml: str = "/opt/tak/UserAuthenticationFile.xml",
    state_root: str = "/opt/tak/takctl-state/onboarding",
    json_out: bool = True,
) -> str:
    """
    Returns JSON text of joined identity + onboarding state.

    NOTE: state_root must be writable by the running user/service.
    """
    ud = UserDirectoryXml(userauth_xml)
    store = FileJsonOnboardingStore(state_root)
    svc = OnboardingService(ud, store)

    rows = svc.list_users_with_onboarding()

    payload = []
    for r in rows:
        payload.append(
            {
                "username": r.username,
                "groups": list(r.groups),
                "onboarding_status": r.onboarding_status.value,
                "onboarding": None if r.onboarding is None else _record_to_dict(r.onboarding),
            }
        )

    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _record_to_dict(rec):
    # rec is OnboardingRecord; make datetime JSON-safe
    d = asdict(rec)
    if d.get("package") and d["package"].get("generated_at"):
        d["package"]["generated_at"] = d["package"]["generated_at"].isoformat()
    if d.get("delivery") and d["delivery"].get("downloaded_at"):
        if d["delivery"]["downloaded_at"] is not None:
            d["delivery"]["downloaded_at"] = d["delivery"]["downloaded_at"].isoformat()
    # enums
    if "status" in d and hasattr(d["status"], "value"):
        d["status"] = d["status"].value
    return d

