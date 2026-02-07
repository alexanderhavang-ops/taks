from __future__ import annotations

import re
from typing import Tuple


_SQL_START = re.compile(r"^\s*(with|select)\b", re.IGNORECASE)
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|grant|revoke|truncate|comment|vacuum|analyze|copy)\b",
    re.IGNORECASE,
)


def looks_like_sql(text: str) -> bool:
    """
    Very cheap pre-filter: does it look like a read-only SQL statement?
    Used to decide whether to run full validation.
    """
    if not isinstance(text, str):
        return False
    return bool(_SQL_START.search(text or ""))


def validate_sql(sql: str) -> Tuple[bool, str | None]:
    """
    Read-only guard:
      - must start with SELECT or WITH
      - single statement (no ';')
      - no mutation keywords
    """
    if not isinstance(sql, str) or not sql.strip():
        return False, "empty_sql"

    s = sql.strip()

    if ";" in s:
        return False, "multi_statement_or_semicolon_disallowed"

    if not looks_like_sql(s):
        return False, "must_start_with_select_or_with"

    if _FORBIDDEN.search(s):
        return False, "mutation_or_admin_keyword_disallowed"

    return True, None
