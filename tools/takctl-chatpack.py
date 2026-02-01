#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import datetime as dt
import fnmatch
import gzip
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


VERSION = "2026-02-01.1"


# -----------------------------
# Redaction / sanitization
# -----------------------------

REDACT_PATTERNS: List[Tuple[re.Pattern[str], str]] = [
    # key=value-ish tokens
    (re.compile(r"(?i)\b(pass(word)?|storepass|secret|token|api[_-]?key)\b(\s*[:=]\s*)(\S+)"), r"\1\3***REDACTED***"),
]

PEM_BLOCK_RE = re.compile(
    r"-----BEGIN (EC |RSA )?PRIVATE KEY-----.*?-----END (EC |RSA )?PRIVATE KEY-----\s*"
    r"|-----BEGIN PRIVATE KEY-----.*?-----END PRIVATE KEY-----\s*"
    r"|-----BEGIN OPENSSH PRIVATE KEY-----.*?-----END OPENSSH PRIVATE KEY-----\s*"
    r"|-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----\s*",
    re.DOTALL,
)


def redact_text(s: str) -> str:
    # Drop PEM blocks
    s = PEM_BLOCK_RE.sub("", s)
    # Pattern redaction
    for rx, repl in REDACT_PATTERNS:
        s = rx.sub(repl, s)
    return s


# -----------------------------
# Text/binary detection
# -----------------------------

def looks_binary(data: bytes) -> bool:
    # NUL byte => very likely binary
    if b"\x00" in data:
        return True
    return False


def read_text_file(path: Path, max_bytes: int) -> Tuple[Optional[str], str]:
    """
    Returns (text, reason).
    If text is None, reason explains why it was skipped.
    """
    try:
        size = path.stat().st_size
    except Exception as e:
        return None, f"stat failed: {e}"

    if size > max_bytes:
        return None, f"skipped: {size} bytes > MAX_BYTES={max_bytes}"

    try:
        data = path.read_bytes()
    except Exception as e:
        return None, f"read failed: {e}"

    if looks_binary(data):
        return None, "skipped: contains NUL byte; likely binary"

    # Decode best-effort; if it explodes, treat as binary-ish
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        # Try latin-1 fallback (common for some conf/logs)
        try:
            text = data.decode("latin-1")
        except Exception:
            return None, "skipped: undecodable text (utf-8/latin-1)"

    return text, "ok"


def lang_hint(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".py": "python",
        ".sh": "bash",
        ".conf": "nginx",
        ".service": "ini",
        ".toml": "toml",
        ".xml": "xml",
        ".js": "javascript",
        ".css": "css",
        ".md": "markdown",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".json": "json",
    }.get(ext, "")


# -----------------------------
# File selection
# -----------------------------

DEFAULT_EXCLUDES = [
    "takctl/backup/**",
    "takctl/ignite/work/**",
    "takctl/secrets/**",
    "**/__pycache__/**",
    "**/*.pyc",
    "**/node_modules/**",
    "**/vendor/**",
    "**/*.min.js",
    # common cert/key material (keep services.crl explicitly)
    "**/*.p12",
    "**/*.jks",
    "**/*.key",
    "**/*.pem",
    "**/*.crt",
    "**/*.csr",
    "**/*.crl",
]

DEFAULT_INCLUDES = [
    "infra/**",
    "tools/**",
    "takctl/pyproject.toml",
    "takctl/takctl.conf",
    "takctl/takctl/**",
    "takctl/bin/**",
    "takctl/tests/**",
    # optional web (off by default; enable via --include-web)
    # "takctl/web/**",
]

# This file is special: we want it even though it ends with .crl
FORCE_INCLUDE = [
    "takctl/takctl/services.crl",
]


def glob_match(path_str: str, patterns: List[str]) -> bool:
    # support ** by normalizing to fnmatch on POSIX-ish paths
    p = path_str.replace(os.sep, "/")
    for pat in patterns:
        patn = pat.replace(os.sep, "/")
        if fnmatch.fnmatch(p, patn):
            return True
    return False


def iter_repo_files(repo_root: Path) -> List[str]:
    """
    Prefer git ls-files when available; fallback to filesystem walk.
    Returns repo-relative POSIX paths.
    """
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        if r.returncode == 0:
            r2 = subprocess.run(
                ["git", "ls-files"],
                cwd=str(repo_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
            )
            if r2.returncode == 0:
                files = [line.strip() for line in r2.stdout.splitlines() if line.strip()]
                return sorted(set(files))
    except Exception:
        pass

    out: List[str] = []
    for p in repo_root.rglob("*"):
        if p.is_file():
            out.append(str(p.relative_to(repo_root)).replace(os.sep, "/"))
    return sorted(set(out))


def select_files(
    repo_root: Path,
    include_globs: List[str],
    exclude_globs: List[str],
    include_web: bool,
) -> List[str]:
    files = iter_repo_files(repo_root)

    inc = include_globs[:]
    exc = exclude_globs[:]

    if include_web:
        inc.append("takctl/web/**")
        # still exclude vendor/minified via DEFAULT_EXCLUDES

    selected: List[str] = []

    # Always include forced paths if they exist in repo
    force_set = set(FORCE_INCLUDE)

    for rel in files:
        if rel in force_set:
            selected.append(rel)
            continue

        # must match an include glob
        if not glob_match(rel, inc):
            continue

        # must NOT match excludes
        if glob_match(rel, exc):
            continue

        selected.append(rel)

    # stable ordering, but keep forced files near their natural position already
    return sorted(set(selected))


# -----------------------------
# Architecture notes
# -----------------------------

ARCH_DOC_CANDIDATES = [
    "infra/notes/architecture.md",
    "docs/takctl-ARCHITECTURE.md",
    "docs/ARCHITECTURE.md",
]


def load_architecture_notes(repo_root: Path, max_bytes: int) -> str:
    for rel in ARCH_DOC_CANDIDATES:
        p = repo_root / rel
        if p.exists() and p.is_file():
            txt, reason = read_text_file(p, max_bytes=max_bytes)
            if txt is not None:
                return f"### From `{rel}`\n\n" + redact_text(txt).strip() + "\n"
            return f"### `{rel}` ({reason})\n"
    # fallback minimal scaffold
    return (
        "### Notes\n\n"
        "- Add wiring/ports/endpoints assumptions here in-repo so chatpack stays useful.\n"
        "- Suggested: infra/notes/architecture.md\n"
    )


# -----------------------------
# Runtime snapshot
# -----------------------------

def run_cmd(cmd: List[str], cwd: Optional[Path] = None, limit_lines: int = 120) -> str:
    try:
        r = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        out = r.stdout or ""
    except Exception as e:
        return f"(failed to run {cmd!r}: {e})\n"

    lines = out.splitlines()
    out2 = "\n".join(lines[:limit_lines]) + ("\n" if lines else "")
    return redact_text(out2)


def runtime_snapshot() -> str:
    parts: List[str] = []
    parts.append("## Runtime snapshot (sanitized)\n")
    parts.append(f"Collected: {dt.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}\n\n")

    parts.append("### systemd: takctl-web.service (short)\n\n```text\n")
    parts.append(run_cmd(["systemctl", "--no-pager", "-l", "status", "takctl-web.service"], limit_lines=80))
    parts.append("```\n\n")

    parts.append("### nginx: sites-enabled listing\n\n```text\n")
    parts.append(run_cmd(["bash", "-lc", "ls -l /etc/nginx/sites-enabled 2>/dev/null || true"], limit_lines=120))
    parts.append("```\n\n")

    parts.append("### takctl-web: openapi paths (best-effort)\n\n```text\n")
    # curl openapi, print paths if possible
    try:
        r = subprocess.run(
            ["bash", "-lc", "curl -fsS http://127.0.0.1:8080/openapi.json 2>/dev/null || true"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        raw = r.stdout.strip()
        if raw:
            j = json.loads(raw)
            paths = sorted(j.get("paths", {}).keys())
            parts.append("\n".join(paths) + "\n")
        else:
            parts.append("(no openapi.json)\n")
    except Exception as e:
        parts.append(f"(failed to read openapi.json: {e})\n")
    parts.append("```\n\n")

    return "".join(parts)


# -----------------------------
# Markdown assembly
# -----------------------------

def md_header(repo_root: Path) -> str:
    return (
        "# takctl context bundle\n\n"
        f"Generated: {dt.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        f"Version: {VERSION}\n"
        f"Repo root: {repo_root}\n\n"
        "Paste this entire document into a new chat to restore takctl context.\n\n"
    )


def md_repo_tree(selected: List[str]) -> str:
    head = "## Repository tree (filtered)\n\n"
    body = "\n".join(selected[:800]) + ("\n" if selected else "")
    if len(selected) > 800:
        body += f"\n_Truncated tree: showing 800 of {len(selected)} files._\n"
    return head + body + "\n"


def md_arch_section(arch: str) -> str:
    return "## Architecture / wiring\n\n" + arch.strip() + "\n\n"


def md_file_block(rel: str, text: str) -> str:
    lang = lang_hint(Path(rel))
    fence = f"```{lang}\n" if lang else "```\n"
    return f"### `{rel}`\n\n{fence}{redact_text(text).rstrip()}\n```\n\n"


def build_markdown(
    repo_root: Path,
    selected_files: List[str],
    max_files: int,
    max_bytes: int,
    with_runtime: bool,
) -> str:
    out: List[str] = []
    out.append(md_header(repo_root))

    arch = load_architecture_notes(repo_root, max_bytes=max_bytes)
    out.append(md_arch_section(arch))

    out.append(md_repo_tree(selected_files))

    out.append("## Key files (contents)\n\n")

    count = 0
    for rel in selected_files:
        if count >= max_files:
            out.append(f"_Truncated: reached MAX_FILES={max_files}_\n\n")
            break

        abs_path = repo_root / rel
        if not abs_path.exists():
            continue

        txt, reason = read_text_file(abs_path, max_bytes=max_bytes)
        if txt is None:
            out.append(f"### `{rel}` ({reason})\n\n")
            count += 1
            continue

        out.append(md_file_block(rel, txt))
        count += 1

    if with_runtime:
        out.append(runtime_snapshot())

    return "".join(out)


# -----------------------------
# Output encodings
# -----------------------------

def emit_plain(data: bytes, out_path: Optional[Path]) -> None:
    if out_path:
        out_path.write_bytes(data)
    else:
        sys.stdout.buffer.write(data)


def emit_b64_gzip(text: str, out_path: Optional[Path]) -> None:
    raw = text.encode("utf-8")
    gz = gzip.compress(raw, compresslevel=9)
    b64 = base64.b64encode(gz)

    header = (
        "# takctl chatpack (gzip+base64)\n\n"
        "Unpack on the box:\n\n"
        "```bash\n"
        "base64 -d /tmp/takctl-context.md.b64 | gunzip > /tmp/takctl-context.md\n"
        "```\n\n"
        "Payload:\n\n"
    ).encode("utf-8")

    payload = header + b64 + b"\n"
    emit_plain(payload, out_path)


# -----------------------------
# CLI
# -----------------------------

@dataclass
class Args:
    out: Optional[str]
    with_runtime: bool
    max_bytes: int
    max_files: int
    include_web: bool
    include: List[str]
    exclude: List[str]
    b64_gzip: bool


def parse_args(argv: List[str]) -> Args:
    p = argparse.ArgumentParser(description="takctl chat context packer (markdown bundle)")
    p.add_argument("--out", help="write output to file instead of stdout")
    p.add_argument("--with-runtime", action="store_true", help="include sanitized runtime snapshot")
    p.add_argument("--max-bytes", type=int, default=int(os.environ.get("MAX_BYTES", "200000")),
                   help="per-file max bytes (default 200000 or env MAX_BYTES)")
    p.add_argument("--max-files", type=int, default=int(os.environ.get("MAX_FILES", "250")),
                   help="max number of files included (default 250 or env MAX_FILES)")
    p.add_argument("--include-web", action="store_true", help="include takctl/web (excluding vendor/minified)")
    p.add_argument("--include", action="append", default=[], help="extra include glob (repeatable)")
    p.add_argument("--exclude", action="append", default=[], help="extra exclude glob (repeatable)")
    p.add_argument("--b64-gzip", action="store_true", help="emit as gzip+base64 payload (paste-resilient)")
    ns = p.parse_args(argv)

    return Args(
        out=ns.out,
        with_runtime=bool(ns.with_runtime),
        max_bytes=int(ns.max_bytes),
        max_files=int(ns.max_files),
        include_web=bool(ns.include_web),
        include=list(ns.include),
        exclude=list(ns.exclude),
        b64_gzip=bool(ns.b64_gzip),
    )


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]

    include_globs = DEFAULT_INCLUDES + args.include
    exclude_globs = DEFAULT_EXCLUDES + args.exclude

    selected = select_files(
        repo_root=repo_root,
        include_globs=include_globs,
        exclude_globs=exclude_globs,
        include_web=args.include_web,
    )

    md = build_markdown(
        repo_root=repo_root,
        selected_files=selected,
        max_files=args.max_files,
        max_bytes=args.max_bytes,
        with_runtime=args.with_runtime,
    )

    out_path = Path(args.out).resolve() if args.out else None
    if args.b64_gzip:
        emit_b64_gzip(md, out_path)
    else:
        emit_plain(md.encode("utf-8"), out_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

