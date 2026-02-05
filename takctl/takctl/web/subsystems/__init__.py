from __future__ import annotations

import importlib
import pkgutil
import traceback
from dataclasses import dataclass, asdict
from typing import Any

# NOTE:
# - Best-effort discovery: failures are recorded, never raised.
# - Subsystems are Python modules in this package (takctl.web.subsystems.*)
# - Each module may expose:
#     NAME: str
#     def register(app) -> dict | None
#   where register() should include routes/middleware/etc and return metadata.

@dataclass
class SubsystemStatus:
    name: str
    loaded: bool
    error: str | None = None
    detail: str | None = None

_STATUS: dict[str, SubsystemStatus] = {}

def _record(name: str, loaded: bool, error: str | None = None, detail: str | None = None) -> None:
    _STATUS[name] = SubsystemStatus(name=name, loaded=loaded, error=error, detail=detail)

def load_subsystems(app: Any) -> dict[str, dict[str, Any]]:
    """
    Discover and register subsystems from takctl.web.subsystems.*.
    Returns a dict of subsystem name -> return value from register() (if any).
    """
    results: dict[str, dict[str, Any]] = {}

    pkg_name = __name__
    pkg = importlib.import_module(pkg_name)
    for m in pkgutil.iter_modules(pkg.__path__, pkg_name + "."):
        modname = m.name

        # Name defaults to module leaf (e.g. takctl.web.subsystems.llm -> llm)
        leaf = modname.rsplit(".", 1)[-1]
        name = leaf

        try:
            mod = importlib.import_module(modname)
            name = getattr(mod, "NAME", name)

            reg = getattr(mod, "register", None)
            if callable(reg):
                meta = reg(app) or {}
                if not isinstance(meta, dict):
                    meta = {"meta": str(meta)}
                results[name] = meta
                _record(name, True)
            else:
                _record(name, False, "no-register", f"{modname} has no register(app)")
        except Exception as e:
            _record(name, False, type(e).__name__, traceback.format_exc(limit=50))

    return results

def get_subsystems_status() -> dict[str, Any]:
    return {k: asdict(v) for k, v in sorted(_STATUS.items(), key=lambda kv: kv[0])}
