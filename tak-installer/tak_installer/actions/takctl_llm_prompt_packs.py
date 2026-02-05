from __future__ import annotations

import shutil
from pathlib import Path

from tak_installer.util import log

# Git defaults (seed material in repo)
DEFAULTS_ROOT = Path("/opt/taks/llm-infra/llm/prompt-packs")

# Runtime overrides (editable: UI/shell/orchestrator)
OVERRIDES_ROOT = Path("/opt/tak/tools/takctl/user-uploads/llm/prompt-packs")

# Deployed active set (installer-owned; what takctl should read)
DEST_ROOT = Path("/opt/tak/tools/takctl/llm/prompt-packs")

REQUIRED = ("system.txt", "user.txt")


def _has_required(d: Path) -> bool:
    return all((d / f).is_file() for f in REQUIRED)


def _views_under(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {p.name for p in root.iterdir() if p.is_dir()}


def _deploy_view(src: Path, dst: Path) -> None:
    # Replace destination view dir deterministically
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)


def apply(ctx) -> None:
    DEST_ROOT.mkdir(parents=True, exist_ok=True)

    views = sorted(_views_under(DEFAULTS_ROOT) | _views_under(OVERRIDES_ROOT))
    if not views:
        raise RuntimeError(
            "no LLM prompt packs found "
            f"(defaults={DEFAULTS_ROOT} overrides={OVERRIDES_ROOT})"
        )

    for view in views:
        o_dir = OVERRIDES_ROOT / view
        d_dir = DEFAULTS_ROOT / view
        dst = DEST_ROOT / view

        if o_dir.exists() and _has_required(o_dir):
            log.info(f"takctl.llm-prompt-packs: view={view} source=override path={o_dir}")
            _deploy_view(o_dir, dst)
            continue

        if d_dir.exists() and _has_required(d_dir):
            log.info(f"takctl.llm-prompt-packs: view={view} source=default path={d_dir}")
            _deploy_view(d_dir, dst)
            continue

        raise RuntimeError(
            f"invalid prompt pack for view '{view}': missing required files {REQUIRED} "
            f"(override={'present' if o_dir.exists() else 'absent'} "
            f"default={'present' if d_dir.exists() else 'absent'})"
        )


class _Action:
    ID = "takctl.llm-prompt-packs"

    def inspect(self, ctx) -> int:
        log.info(f"Inspecting {self.ID} action...")
        log.info(f"  defaults:  {DEFAULTS_ROOT}")
        log.info(f"  overrides: {OVERRIDES_ROOT}")
        log.info(f"  dest:      {DEST_ROOT}")

        views = sorted(_views_under(DEFAULTS_ROOT) | _views_under(OVERRIDES_ROOT))
        log.info(f"  views:     {', '.join(views) if views else '(none)'}")
        return 0

    def apply(self, ctx) -> int:
        log.info(f"Applying {self.ID} action...")
        apply(ctx)
        return 0


ACTION = _Action()
