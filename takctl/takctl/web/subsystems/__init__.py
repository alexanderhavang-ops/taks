from __future__ import annotations

import importlib
import pkgutil
import traceback
from dataclasses import dataclass, asdict
from typing import Any

from fastapi import FastAPI


@dataclass
class SubsystemStatus:
    name: str
    ok: bool
    detail: dict[str, Any]


# Global snapshot (best-effort; safe if empty)
_STATUS: dict[str, SubsystemStatus] = {}


def _record(name: str, ok: bool, detail: dict[str, Any]) -> None:
    _STATUS[name] = SubsystemStatus(name=name, ok=ok, detail=detail)


def load_subsystems(app: FastAPI) -> dict[str, Any]:
    """
    Discover and load optional web subsystems.

    Contract:
      - Any module under takctl.web.subsystems.* may define:
          def init(app: FastAPI) -> dict:   (required to be loadable)
      - init() should raise only if it truly cannot load; loader will catch and mark failed.

    This function MUST NOT raise (best-effort).
    """
    # Import ourselves to get package path for scanning
    pkg = importlib.import_module(__name__)  # takctl.web.subsystems

    loaded: list[str] = []
    failed: list[str] = []

    # Walk modules in this package (no recursion by default)
    for m in pkgutil.iter_modules(pkg.__path__):  # type: ignore[attr-defined]
        modname = m.name

        # Skip private helpers
        if modname.startswith("_"):
            continue
        # Skip this __init__ pseudo-module
        if modname in ("__init__",):
            continue

        fq = f"{__name__}.{modname}"
        try:
            mod = importlib.import_module(fq)

            if not hasattr(mod, "init"):
                _record(
                    modname,
                    ok=False,
                    detail={"error": "missing_init", "module": fq},
                )
                failed.append(modname)
                continue

            init_fn = getattr(mod, "init")
            res = init_fn(app)

            if isinstance(res, dict):
                name = str(res.get("name") or modname)
                ok = bool(res.get("ok", True))
                _record(name, ok=ok, detail=res)
            else:
                _record(
                    modname,
                    ok=True,
                    detail={"name": modname, "ok": True, "note": "init_returned_non_dict"},
                )

            loaded.append(modname)

        except Exception as e:
            _record(
                modname,
                ok=False,
                detail={
                    "name": modname,
                    "ok": False,
                    "error": f"{type(e).__name__}: {e}",
                    "traceback": traceback.format_exc(limit=6),
                    "module": fq,
                },
            )
            failed.append(modname)

    return {
        "ok": True,
        "loaded": loaded,
        "failed": failed,
        "count": {"loaded": len(loaded), "failed": len(failed)},
    }


def get_subsystems_status() -> dict[str, Any]:
    """
    Return current subsystem status as JSON-safe dict.
    """
    return {
        "ok": True,
        "subsystems": {k: asdict(v) for k, v in sorted(_STATUS.items(), key=lambda kv: kv[0])},
    }

