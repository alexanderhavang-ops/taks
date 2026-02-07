from __future__ import annotations

import os
import pwd
import grp
from pathlib import Path
from tak_installer.util import log


STATE_ROOT = Path("/opt/tak/takctl-state")
ONBOARDING_DIR = STATE_ROOT / "onboarding"
ONBOARDING_USERS_DIR = ONBOARDING_DIR / "users"


def _chown(path: Path, user: str, group: str) -> None:
    uid = pwd.getpwnam(user).pw_uid
    gid = grp.getgrnam(group).gr_gid
    os.chown(path, uid, gid)


def apply(ctx) -> None:
    """
    Create takctl runtime state directories (installer-owned).

      /opt/tak/takctl-state/
      /opt/tak/takctl-state/onboarding/
      /opt/tak/takctl-state/onboarding/users/

    Write model:
      - owner: tak:tak
      - mode: 0770 (so admins in group 'tak' can write)
    """
    user = "tak"
    group = "tak"
    mode = 0o770

    log.info("takctl-state: ensuring runtime state directories exist")
    log.info(f"  state_root: {STATE_ROOT}")
    log.info(f"  onboarding: {ONBOARDING_DIR}")
    log.info(f"  users:     {ONBOARDING_USERS_DIR}")
    log.info(f"  owner: {user}:{group} mode={oct(mode)}")

    for d in (STATE_ROOT, ONBOARDING_DIR, ONBOARDING_USERS_DIR):
        d.mkdir(parents=True, exist_ok=True)
        _chown(d, user, group)
        d.chmod(mode)

    log.info("takctl-state: ready")


class _Action:
    ID = "takctl-state"

    def inspect(self, ctx) -> int:
        print(f"Inspecting {self.ID} action...")
        ok = STATE_ROOT.exists() and ONBOARDING_DIR.exists() and ONBOARDING_USERS_DIR.exists()
        return 0 if ok else 1

    def apply(self, ctx) -> int:
        print(f"Applying {self.ID} action...")
        apply(ctx)
        return 0


ACTION = _Action()

