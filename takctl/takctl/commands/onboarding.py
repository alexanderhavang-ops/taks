from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

from takctl.appctx import AppContext
from takctl.onboarding.service import OnboardingService
from takctl.onboarding.store_filejson import FileJsonOnboardingStore
from takctl.onboarding.user_directory_xml import UserDirectoryXml

app = typer.Typer(help="Onboarding (state + packaging metadata). Identity is external; takctl observes only.")


def _col(s: str, w: int) -> str:
    s = s or ""
    return s[:w].ljust(w)


def _print_status_human(data: Dict[str, Any]) -> None:
    users: List[Dict[str, Any]] = data.get("users", [])
    unknown: List[Dict[str, Any]] = data.get("unknown_endpoints", [])

    print()
    print("USERS (authoritative: UserAuthenticationFile.xml)")
    print("─" * 96)
    print(
        f"{_col('USERNAME', 24)} "
        f"{_col('GROUPS', 14)} "
        f"{_col('ONBOARD', 10)} "
        f"{_col('CoT', 4)} "
        f"{_col('RECENT', 6)} "
        f"{_col('AGE', 8)} "
        f"CALLSIGN/UID"
    )
    print("─" * 96)

    for u in users:
        act = u.get("activity") or None

        cot = "—"
        recent = "—"
        age = "—"
        tail = "—"

        if act:
            cot = "YES" if act.get("cot_seen") else "—"
            recent = "YES" if act.get("seen_recently") else "NO"
            age = act.get("age_human") or "—"
            callsign = act.get("callsign") or ""
            uid = act.get("uid") or ""
            tail = f"{callsign} {uid}".strip()

        print(
            f"{_col(u.get('username', ''), 24)} "
            f"{_col(','.join(u.get('groups') or []), 14)} "
            f"{_col(str(u.get('onboarding_status', '')).upper(), 10)} "
            f"{_col(cot, 4)} "
            f"{_col(recent, 6)} "
            f"{_col(age, 8)} "
            f"{tail}"
        )

    if unknown:
        print()
        print("UNMANAGED ENDPOINTS (seen in DB but not in XML)")
        print("─" * 96)
        print(
            f"{_col('USERNAME', 24)} "
            f"{_col('CALLSIGN', 12)} "
            f"{_col('RECENT', 6)} "
            f"{_col('AGE', 8)} "
            f"UID"
        )
        print("─" * 96)
        for e in unknown:
            recent = e.get("seen_recently")
            recent_s = "YES" if recent is True else ("NO" if recent is False else "—")
            print(
                f"{_col(e.get('username', ''), 24)} "
                f"{_col(e.get('callsign') or '—', 12)} "
                f"{_col(recent_s, 6)} "
                f"{_col(e.get('age_human') or '—', 8)} "
                f"{e.get('uid','')}"
            )

    print()


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


@app.command("status")
def status_cmd(
    ctx: typer.Context,
    unknown_limit: int = typer.Option(50, "--unknown-limit", help="Max unmanaged endpoints to include"),
    recent_minutes: int = typer.Option(120, "--recent-minutes", help="Mark seen_recently when last CoT <= this many minutes"),
) -> None:
    appctx: AppContext = ctx.obj["appctx"]

    # Keep these stable (installer-owned runtime paths)
    userauth_xml = "/opt/tak/UserAuthenticationFile.xml"
    state_root = Path("/opt/tak/takctl-state/onboarding")

    ud = UserDirectoryXml(userauth_xml)
    store = FileJsonOnboardingStore(state_root)
    svc = OnboardingService(ud, store)

    db = getattr(appctx, "db", None)
    out = svc.status(db=db, unknown_limit=int(unknown_limit), recent_minutes=int(recent_minutes))

    want_json = bool((ctx.obj or {}).get("json", False))
    if want_json:
        _print_json(out)
    else:
        _print_status_human(out)
