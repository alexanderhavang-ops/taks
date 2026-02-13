#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from typing import List, Tuple

BASE = os.environ.get("BASE", "https://127.0.0.1").rstrip("/")
MOUNT = os.environ.get("MOUNT", "/takctl")
URL_BASE = f"{BASE}{MOUNT}"

STRICT = os.environ.get("STRICT", "").strip().lower() in ("1", "true", "yes", "on")
TIMEOUT_MS = int(os.environ.get("TIMEOUT_MS", "12000"))

# Comma-separated substrings; any failing URL containing one of these is ignored
IGNORE_URL_SUBSTR = [s for s in os.environ.get("IGNORE_URL_SUBSTR", "").split(",") if s.strip()]
# Handy default you can enable by setting IGNORE_URL_SUBSTR="/favicon.ico"
PAGES = [
    f"{URL_BASE}/",
    f"{URL_BASE}/splash.html",
]

def warn(msg: str) -> None:
    print(f"WARN: {msg}", file=sys.stderr)

def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)

def ok(msg: str) -> None:
    print(f"OK:   {msg}")

def _ignored(url: str) -> bool:
    return any(sub in url for sub in IGNORE_URL_SUBSTR)

def main() -> int:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as e:
        msg = f"playwright not available ({e}). Skipping JS/runtime checks."
        if STRICT:
            fail(msg)
        warn(msg)
        return 0

    console_errors: List[Tuple[str, str]] = []
    page_errors: List[Tuple[str, str]] = []
    request_failed: List[Tuple[str, str]] = []
    bad_responses: List[Tuple[str, int]] = []

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, args=["--ignore-certificate-errors"])
        except Exception as e:
            msg = f"playwright chromium launch failed ({e})"
            if STRICT:
                fail(msg)
            warn(msg)
            return 0

        ctx = browser.new_context(ignore_https_errors=True)

        def attach(page, label: str):
            def on_console(msg):
                # "Failed to load resource: the server responded with a status of 404" is console.error
                if msg.type == "error":
                    console_errors.append((label, f"console.error: {msg.text}"))

            def on_pageerror(exc):
                page_errors.append((label, f"pageerror: {exc}"))

            def on_requestfailed(req):
                u = req.url
                if _ignored(u):
                    return
                request_failed.append((label, f"requestfailed: {u} ({req.failure.error_text if req.failure else 'unknown'})"))

            def on_response(resp):
                st = resp.status
                u = resp.url
                if st >= 400 and not _ignored(u):
                    bad_responses.append((u, st))

            page.on("console", on_console)
            page.on("pageerror", on_pageerror)
            page.on("requestfailed", on_requestfailed)
            page.on("response", on_response)

        for url in PAGES:
            page = ctx.new_page()
            attach(page, url)
            ok(f"open {url}")
            page.goto(url, wait_until="load", timeout=TIMEOUT_MS)
            # Give late JS + fetches time to fire
            page.wait_for_timeout(800)
            page.close()

        ctx.close()
        browser.close()

    # De-dupe and sort response failures
    bad_responses_unique = sorted({(u, st) for (u, st) in bad_responses}, key=lambda x: (x[1], x[0]))

    if bad_responses_unique or request_failed or page_errors or console_errors:
        print("JS/RESOURCE ISSUES DETECTED:")

        if bad_responses_unique:
            print("\nHTTP failures (status>=400):")
            for u, st in bad_responses_unique:
                print(f"- {st} {u}")

        if request_failed:
            print("\nNetwork request failures:")
            for label, msg in request_failed:
                print(f"- {label}\n  {msg}")

        if page_errors:
            print("\nJS exceptions (pageerror):")
            for label, msg in page_errors:
                print(f"- {label}\n  {msg}")

        if console_errors:
            print("\nConsole errors:")
            for label, msg in console_errors:
                print(f"- {label}\n  {msg}")

        if STRICT:
            return 1
        return 0

    ok("No JS/runtime console errors, no request failures, no HTTP>=400 responses.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
