from __future__ import annotations

from pathlib import Path

from tak_installer.util import log

RUNTIME_DIR = Path("/opt/tak/tools/takctl")
UPLOADS_DIR = RUNTIME_DIR / "user-uploads"
ASSETS_DIR = RUNTIME_DIR / "web" / "assets"


def _unlink_any(path: Path) -> None:
    try:
        if path.is_symlink() or path.exists():
            path.unlink()
    except Exception:
        # Best-effort cleanup; don't hard-fail the installer on weird FS states.
        pass


def _link_if_exists(src: Path, dst: Path) -> bool:
    """
    If src exists, ensure dst is a symlink to src. Returns True if linked.
    """
    if not src.exists():
        return False

    dst.parent.mkdir(parents=True, exist_ok=True)
    _unlink_any(dst)

    try:
        dst.symlink_to(src)
    except Exception as e:
        raise RuntimeError(f"failed to symlink {dst} -> {src}: {e}") from e

    return True


def apply(ctx) -> None:
    # Ensure the runtime-owned directory exists (not in /opt/taks).
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    # Create/refresh symlinks for logo1/2/3 in BOTH svg and png forms if present.
    for n in (1, 2, 3):
        has_any = False

        has_any |= _link_if_exists(
            UPLOADS_DIR / f"logo{n}.svg",
            ASSETS_DIR / f"logo{n}.svg",
        )
        has_any |= _link_if_exists(
            UPLOADS_DIR / f"logo{n}.png",
            ASSETS_DIR / f"logo{n}.png",
        )

        if has_any:
            log.info(f"takctl-user-uploads: linked logo{n}.* from user-uploads")
        else:
            log.info(f"takctl-user-uploads: no logo{n}.svg/.png in user-uploads (skipped)")

    # slogan.txt: prefer user-uploads version, link into web/assets
    if _link_if_exists(UPLOADS_DIR / "slogan.txt", ASSETS_DIR / "slogan.txt"):
        log.info("takctl-user-uploads: linked slogan.txt from user-uploads")
    else:
        log.info("takctl-user-uploads: no slogan.txt in user-uploads (skipped)")


class _Action:
    ID = "takctl-user-uploads"

    def inspect(self, ctx) -> int:
        log.info(f"Inspecting {self.ID} action...")
        return 0

    def apply(self, ctx) -> int:
        log.info(f"Applying {self.ID} action...")
        apply(ctx)
        return 0


ACTION = _Action()

