from __future__ import annotations
import re

_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    # AWS env-style assignments
    (re.compile(r'(?im)^(AWS_SECRET_ACCESS_KEY|aws_secret_access_key)\s*=\s*.*$'), r'\1=REDACTED'),
    (re.compile(r'(?im)^(AWS_ACCESS_KEY_ID|aws_access_key_id)\s*=\s*.*$'), r'\1=REDACTED'),
    (re.compile(r'(?im)^(AWS_SESSION_TOKEN|aws_session_token)\s*=\s*.*$'), r'\1=REDACTED'),

    # generic password-ish assignments (best-effort; can over-redact)
    (re.compile(r'(?im)^(password|pass|passphrase|token|secret)\s*=\s*.*$'), r'\1=REDACTED'),

    # bearer tokens in headers
    (re.compile(r'(?i)(Authorization:\s*Bearer)\s+[A-Za-z0-9\._-]+'), r'\1 REDACTED'),
]

def redact_text(s: str) -> str:
    out = s
    for pat, rep in _REPLACEMENTS:
        out = pat.sub(rep, out)
    return out
