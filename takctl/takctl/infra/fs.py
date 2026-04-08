from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tempfile

from takctl.config import RuntimeConfig


@dataclass
class FS:
    cfg: RuntimeConfig

    def read_text(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8")

    def atomic_write_bytes(self, path: str, data: bytes, mode: int = 0o644) -> None:
        """
        Atomic write: write temp file in same directory then rename.
        """
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=p.name + ".", dir=str(p.parent))
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, mode)
            os.replace(tmp, str(p))
        finally:
            try:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            except Exception:
                pass
