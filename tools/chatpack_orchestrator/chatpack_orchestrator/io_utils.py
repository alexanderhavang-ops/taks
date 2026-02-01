from __future__ import annotations
import sys

def eprint(msg: str) -> None:
    sys.stderr.write(msg.rstrip() + "\n")
