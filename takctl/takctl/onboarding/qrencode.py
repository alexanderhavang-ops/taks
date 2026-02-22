from __future__ import annotations

from pathlib import Path
import subprocess


def write_qr_png(payload: str, out_png: str | Path, *, size: int = 8) -> Path:
    """
    Generate a PNG QR code using system qrencode (no Python deps).
    """
    out = Path(out_png)
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "/usr/bin/qrencode",
        "-o", str(out),
        "-t", "PNG",
        "-s", str(int(size)),
        payload,
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError:
        raise RuntimeError("qrencode not installed at /usr/bin/qrencode")
    except subprocess.CalledProcessError as e:
        msg = (e.stderr or "").strip()
        raise RuntimeError(f"qrencode failed: {msg[:240]}")

    return out
