from __future__ import annotations

import re
from typing import Pattern, Tuple, List


_REDACT_PATTERNS: List[Tuple[Pattern[str], str]] = [
    # common env/secret formats
    (re.compile(r"(AWS_SECRET_ACCESS_KEY\\s*=\\s*)(\\S+)", re.I), r"\\1REDACTED"),
    (re.compile(r"(AWS_SESSION_TOKEN\\s*=\\s*)(\\S+)", re.I), r"\\1REDACTED"),
    (re.compile(r"(AWS_ACCESS_KEY_ID\\s*=\\s*)(\\S+)", re.I), r"\\1REDACTED"),
    (re.compile(r"(password\\s*[=:]\\s*)(\\S+)", re.I), r"\\1REDACTED"),
    (re.compile(r"(token\\s*[=:]\\s*)(\\S+)", re.I), r"\\1REDACTED"),
    (re.compile(r"(apikey\\s*[=:]\\s*)(\\S+)", re.I), r"\\1REDACTED"),
    (re.compile(r"(api_key\\s*[=:]\\s*)(\\S+)", re.I), r"\\1REDACTED"),
    (re.compile(r"(client_secret\\s*[=:]\\s*)(\\S+)", re.I), r"\\1REDACTED"),
    # PEM blocks
    (re.compile(r"-----BEGIN [A-Z ]+-----.*?-----END [A-Z ]+-----", re.S),
     "-----BEGIN REDACTED-----\\n...\\n-----END REDACTED-----"),
]


def redact(text: str) -> str:
    out = text
    for rx, repl in _REDACT_PATTERNS:
        out = rx.sub(repl, out)
    return out
