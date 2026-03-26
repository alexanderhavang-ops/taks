from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def get_taks_state_summary() -> Dict[str, Any]:
    candidates = {
        "tak_runtime": Path("/opt/tak"),
        "tak_tools": Path("/opt/tak/tools"),
        "takctl_state": Path("/opt/tak/tools/takctl/state"),
        "martine_source": Path("/opt/taks/martine"),
    }

    return {
        "paths": {name: str(path) for name, path in candidates.items()},
        "exists": {name: path.exists() for name, path in candidates.items()},
    }
