from __future__ import annotations

import subprocess
from typing import Any


def systemd_show(unit: str) -> dict[str, Any]:
    keys = [
        "ActiveState",
        "SubState",
        "LoadState",
        "UnitFileState",
        "Description",
        "Result",
    ]
    props = ",".join(keys)

    try:
        p = subprocess.run(
            ["systemctl", "show", unit, f"--property={props}", "--no-pager"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        out: dict[str, Any] = {"unit": unit}

        if p.returncode != 0:
            out["error"] = p.stderr.strip() or f"systemctl show rc={p.returncode}"
            return out

        for line in p.stdout.splitlines():
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k] = v

        return out

    except Exception as e:
        return {"unit": unit, "error": str(e)}

