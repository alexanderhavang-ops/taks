from __future__ import annotations

import os
import re
import tempfile
import subprocess
from pathlib import Path

from tak_installer.util import log

RUNTIME_ROOT = Path("/opt/tak/tools/takctl")
RUNTIME_PKG_ROOT = RUNTIME_ROOT / "takctl"
BIN_ROOT = RUNTIME_ROOT / "bin"
SUDOERS_PATH = Path("/etc/sudoers.d/takctl-helpers")

HELPER_REGEXES = [
    re.compile(r'Path\("(/opt/tak/tools/takctl/bin/[^"]+)"\)'),
    re.compile(r"Path\('(/opt/tak/tools/takctl/bin/[^']+)'\)"),
    re.compile(r'HELPER_PATH\s*=\s*"(/opt/tak/tools/takctl/bin/[^"]+)"'),
    re.compile(r"HELPER_PATH\s*=\s*'(/opt/tak/tools/takctl/bin/[^']+)'"),
]


def _run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if p.returncode != 0:
        raise RuntimeError(f"command failed rc={p.returncode}:\n{' '.join(cmd)}\n\n{p.stdout}")
    if (p.stdout or "").strip():
        log.info((p.stdout or "").strip())


def _discover_helpers() -> list[Path]:
    found: set[str] = set()

    if RUNTIME_PKG_ROOT.exists():
        for p in RUNTIME_PKG_ROOT.rglob("*.py"):
            try:
                s = p.read_text(encoding="utf-8")
            except Exception:
                continue
            for rg in HELPER_REGEXES:
                for m in rg.finditer(s):
                    found.add(m.group(1))

    # Fallback for installer-owned helpers in bin/
    if BIN_ROOT.exists():
        for p in BIN_ROOT.iterdir():
            try:
                if not p.is_file():
                    continue
                if not os.access(p, os.X_OK):
                    continue
                name = p.name.lower()
                if (
                    "helper" in name
                    or "usermgr" in name
                    or "signer" in name
                    or "cert" in name
                    or "log" in name
                ):
                    found.add(str(p))
            except Exception:
                continue

    out: list[Path] = []
    for raw in sorted(found):
        p = Path(raw)
        try:
            if p.is_file() and os.access(p, os.X_OK):
                out.append(p)
        except Exception:
            continue
    return out


def _render(helpers: list[Path]) -> str:
    rows = [
        "# Managed by tak-installer",
        "Defaults:tak !requiretty",
    ]
    for h in helpers:
        rows.append(f"tak ALL=(root) NOPASSWD: {h}, {h} *")
    return "\n".join(rows) + "\n"


def apply(ctx) -> None:
    helpers = _discover_helpers()
    if not helpers:
        raise RuntimeError(f"no takctl sudo helpers discovered under {RUNTIME_ROOT}")

    log.info("takctl.sudoers: discovered helpers:")
    for h in helpers:
        log.info("  %s", h)

    rendered = _render(helpers)

    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tf:
        tf.write(rendered)
        tmp = Path(tf.name)

    try:
        _run(["install", "-m", "0440", str(tmp), str(SUDOERS_PATH)])
        _run(["visudo", "-cf", str(SUDOERS_PATH)])
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass

    log.info("takctl.sudoers: ready")


class _Action:
    ID = "takctl.sudoers"

    def inspect(self, ctx) -> int:
        print(f"Inspecting {self.ID} action...")
        for h in _discover_helpers():
            print(f"helper: {h}")
        return 0

    def apply(self, ctx) -> int:
        print(f"Applying {self.ID} action...")
        apply(ctx)
        return 0


ACTION = _Action()
