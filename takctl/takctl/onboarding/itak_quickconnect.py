from __future__ import annotations


def qr_payload(package_url: str, host: str, port: int | None = None, use_ssl: bool | None = None) -> str:
    del package_url
    p = 8446 if port is None else int(port)
    ssl_mode = "ssl" if (True if use_ssl is None else bool(use_ssl)) else "tcp"
    return f"TAK Server,{host},{p},{ssl_mode}"
