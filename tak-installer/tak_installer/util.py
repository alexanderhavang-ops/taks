from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import logging

# Set up logging
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)
# Optional: add a handler if you want logs to go somewhere specific (e.g., a file)
# logging.basicConfig(filename='/path/to/logfile.log', level=logging.INFO)



def sha256_path(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def diff_text(a: Path, b: Path) -> str:
    try:
        cp = run(["diff", "-u", str(a), str(b)], check=False)
        return cp.stdout
    except FileNotFoundError:
        return "(diff not available)\n"
