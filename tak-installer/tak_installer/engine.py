from __future__ import annotations

import importlib
import pkgutil
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Protocol

import tak_installer.actions



STATE_LOG = Path("/var/log/taks-installer-state.log")


def _ts_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log_state(name: str, status: str) -> None:
    try:
        with STATE_LOG.open("a", encoding="utf-8") as f:
            f.write(f"{name},{_ts_now()},{status}\n")
    except Exception:
        pass


class Action(Protocol):
    ID: str
    def inspect(self, ctx: "Context") -> int: ...
    def apply(self, ctx: "Context") -> int: ...


@dataclass(frozen=True)
class Context:
    repo_root: Path
    dry_run: bool
    env: dict[str, str]


def discover_actions() -> Dict[str, Action]:
    actions: Dict[str, Action] = {}
    pkg = tak_installer.actions

    for m in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + "."):
        mod = importlib.import_module(m.name)
        obj = getattr(mod, "ACTION", None)
        if obj is None:
            continue
        action_id = getattr(obj, "ID", None)
        if not action_id:
            continue
        if action_id in actions:
            raise RuntimeError(f"duplicate action ID: {action_id}")
        actions[action_id] = obj

    return actions


def load_plan_dir(plan_dir: Path) -> list[str]:
    if not plan_dir.is_dir():
        raise FileNotFoundError(f"plan dir not found: {plan_dir}")

    ids: list[str] = []
    for p in sorted(plan_dir.iterdir()):
        if p.name.startswith("."):
            continue
        # Each entry contains an action id (file contents), OR is a symlink whose name *is* the action id.
        if p.is_symlink():
            ids.append(p.name)
            continue
        if p.is_file():
            txt = p.read_text(encoding="utf-8").strip()
            if txt and not txt.startswith("#"):
                ids.append(txt)
    # de-dup while preserving order
    seen = set()
    out: list[str] = []
    for aid in ids:
        if aid in seen:
            continue
        seen.add(aid)
        out.append(aid)
    return out


def run_plan(ctx: Context, plan_ids: Iterable[str]) -> int:
    actions = discover_actions()

    for aid in plan_ids:
        if aid not in actions:
            print(f"ERROR: plan references unknown action: {aid}")
            return 1

        a = actions[aid]
        print()
        print(f"[{a.ID}]")

        _log_state(f"tak-installer:{a.ID}", "Started")
        try:
            rc = a.inspect(ctx) if ctx.dry_run else a.apply(ctx)
        except Exception as e:
            msg = str(e).strip() or e.__class__.__name__
            print(f"ERROR: action raised exception: {a.ID}: {msg}")
            # Common hint for nginx actions
            if "FQDN not set" in msg:
                print("HINT: set node_fqdn in runtime/bootstrap conf.d before running tak-installer apply")
            return 2

        if rc != 0:
            print(f"ERROR: action failed: {a.ID} (rc={rc})")
            return rc

        _log_state(f"tak-installer:{a.ID}", "Succeeded")

    return 0
