#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


# ----------------------------
# Redaction primitives
# ----------------------------

RE_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
RE_FQDN = re.compile(r"\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\b")
RE_HEX_LONG = re.compile(r"\b[A-Fa-f0-9]{32,}\b")
RE_B64ISH_LONG = re.compile(r"\b[A-Za-z0-9+/=_-]{24,}\b")

# Private key / cert markers (content-based tripwires)
RE_PKEY_MARKERS = re.compile(
    r"(BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|AWS_SECRET_ACCESS_KEY|AKIA[0-9A-Z]{16}|-----BEGIN CERTIFICATE-----)"
)

ENV_KEY_REDACTIONS = {
    "LE_EMAIL": "admin@example.invalid",
    "BASE_DOMAIN": "example.invalid",
    "FQDN": "battalion.example.invalid",
    "TAK_UPSTREAM_HOST": "127.0.0.1",
    "TAK_UPSTREAM_PORT": "8447",
    "PUBLIC_PORT_ENROLL": "8446",
}

ENV_PREFIX_REDACT = ("AWS_",)
ENV_SUFFIX_REDACT = ("_TOKEN", "_SECRET", "_PASSWORD", "_PASS")


def redact_env(text: str) -> str:
    """
    Redact env-like KEY=VALUE lines, preserving comments/blank lines.
    Only touches lines that look like simple KEY=... assignments.
    """
    out_lines: list[str] = []
    for line in text.splitlines(keepends=False):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            out_lines.append(line)
            continue

        # Simple KEY=VALUE (no export handling needed; keep it conservative)
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
        if not m:
            out_lines.append(line)
            continue

        key, val = m.group(1), m.group(2)

        if key in ENV_KEY_REDACTIONS:
            out_lines.append(f"{key}={ENV_KEY_REDACTIONS[key]}")
            continue

        if key.startswith(ENV_PREFIX_REDACT) or key.endswith(ENV_SUFFIX_REDACT):
            out_lines.append(f"{key}=REDACTED")
            continue

        # Mild generic redactions inside values
        val2 = RE_EMAIL.sub("admin@example.invalid", val)
        val2 = RE_IPV4.sub("127.0.0.1", val2)
        val2 = RE_FQDN.sub("example.invalid", val2)
        val2 = RE_HEX_LONG.sub("REDACTED", val2)
        val2 = RE_B64ISH_LONG.sub("REDACTED", val2)
        out_lines.append(f"{key}={val2}")

    return "\n".join(out_lines) + ("\n" if text.endswith("\n") else "")


def redact_generic(text: str) -> str:
    """
    Generic redactions for text configs (xml/nginx/conf/ini).
    Tries to preserve structure while removing environment specifics.
    """
    t = text
    t = RE_EMAIL.sub("admin@example.invalid", t)
    t = RE_IPV4.sub("127.0.0.1", t)
    # This will replace any FQDN-like token. If it's too aggressive, we'll tighten it.
    t = RE_FQDN.sub("example.invalid", t)
    t = RE_HEX_LONG.sub("REDACTED", t)
    t = RE_B64ISH_LONG.sub("REDACTED", t)
    return t


# ----------------------------
# File mapping
# ----------------------------

@dataclass(frozen=True)
class Mapping:
    src: Path
    dst: Path
    redactor: Callable[[str], str]


def default_mappings(root: Path) -> list[Mapping]:
    """
    Update these paths to match your repo layout.
    These are sane guesses based on your TAK work so far.
    """
    m: list[Mapping] = []

    m.append(Mapping(root / "installer" / "env", root / "installer" / "env.example", redact_env))
    m.append(Mapping(root / "takctl" / "takctl.conf", root / "takctl" / "takctl.conf.example", redact_generic))
    m.append(Mapping(root / "CoreConfig.xml", root / "CoreConfig.xml.example", redact_generic))

    # nginx/*.conf -> nginx/*.conf.example (if any exist locally)
    nginx_dir = root / "nginx"
    if nginx_dir.is_dir():
        for f in sorted(nginx_dir.glob("*.conf")):
            m.append(Mapping(f, f.with_suffix(f.suffix + ".example"), redact_generic))

    return m


# ----------------------------
# IO + git helpers
# ----------------------------

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def write_text_if_changed(p: Path, text: str) -> bool:
    """
    Writes file only if content differs. Returns True if wrote/changed.
    """
    existing = None
    if p.exists():
        existing = p.read_text(encoding="utf-8", errors="replace")
    if existing == text:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")
    return True


def git_add(paths: Iterable[Path], root: Path) -> None:
    rels = [str(p.relative_to(root)) for p in paths if p.exists()]
    if not rels:
        return
    subprocess.run(["git", "add", "--"] + rels, cwd=str(root), check=False)


def find_repo_root() -> Path:
    # Prefer git if available
    try:
        out = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], stderr=subprocess.DEVNULL, text=True).strip()
        if out:
            return Path(out)
    except Exception:
        pass
    return Path.cwd()


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate sanitized *.example configs from local real configs.")
    ap.add_argument("--stage", action="store_true", help="git add generated *.example files")
    ap.add_argument("--strict", action="store_true", help="fail if any source file is missing")
    ap.add_argument("--check-markers", action="store_true", help="fail if output still contains key/cert markers")
    args = ap.parse_args()

    root = find_repo_root()
    mappings = default_mappings(root)

    changed: list[Path] = []
    missing: list[Path] = []

    for mp in mappings:
        if not mp.src.exists():
            missing.append(mp.src)
            if args.strict:
                continue
            else:
                # skip missing quietly
                continue

        src_text = read_text(mp.src)
        out_text = mp.redactor(src_text)

        if args.check_markers and RE_PKEY_MARKERS.search(out_text):
            raise SystemExit(f"Refusing to write {mp.dst}: still contains key/cert/secret marker patterns")

        if write_text_if_changed(mp.dst, out_text):
            changed.append(mp.dst)

    if args.strict and missing:
        print("sanitize-configs: missing source files (strict mode):")
        for p in missing:
            print(f"  - {p.relative_to(root) if p.is_absolute() else p}")
        return 2

    if args.stage:
        git_add(changed, root)

    if changed:
        print("sanitize-configs: updated:")
        for p in changed:
            print(f"  - {p.relative_to(root)}")
    else:
        print("sanitize-configs: no changes")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
