from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import List, Tuple, Optional

from .redact import redact


@dataclass(frozen=True)
class RunResult:
    rc: int
    out: str


def run(argv: List[str], timeout: int = 10) -> RunResult:
    try:
        p = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
        return RunResult(rc=p.returncode, out=redact(p.stdout or ""))
    except FileNotFoundError as e:
        return RunResult(rc=127, out=str(e))
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") + (e.stderr or "")
        return RunResult(rc=124, out=redact(out) + f"\\n(TIMEOUT after {timeout}s)")
    except Exception as e:
        return RunResult(rc=1, out=str(e))
