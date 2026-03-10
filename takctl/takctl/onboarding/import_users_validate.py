from __future__ import annotations

from typing import Any, Dict, List, Tuple

from takctl.onboarding.import_users import _group_list_from_row

SPECIALS = set(r"-_!@#$%^&*(){}[]+=~`|:;<>,./?")


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _username_valid(username: str) -> Tuple[bool, str | None]:
    u = _norm(username)
    if not u:
        return False, "username is required"
    if any(ch.isspace() for ch in u):
        return False, "username must not contain whitespace"
    return True, None


def _password_strong(password: str) -> Tuple[bool, str | None]:
    p = str(password or "")
    if len(p) < 15:
        return False, "must be at least 15 characters"
    if not any(c.isupper() for c in p):
        return False, "must contain an uppercase letter"
    if not any(c.islower() for c in p):
        return False, "must contain a lowercase letter"
    if not any(c.isdigit() for c in p):
        return False, "must contain a digit"
    if not any(c in SPECIALS for c in p):
        return False, "must contain a special character"
    return True, None


def _issue(row: int, username: str, level: str, code: str, message: str, *, detail: str | None = None) -> Dict[str, Any]:
    out = {
        "row": int(row),
        "username": username,
        "level": level,
        "code": code,
        "message": message,
    }
    if detail:
        out["detail"] = detail
    return out


def validate_rows_static(rows: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Pure static validation:
      - safe on orchestrator before TAK node exists
      - no user directory / Marti / TAK server dependency
    """
    issues: List[Dict[str, Any]] = []
    seen: Dict[str, List[int]] = {}
    unmapped_columns: List[str] = []

    if not rows:
        issues.append(_issue(1, "", "error", "file_empty", "Import file is empty."))
        return {
            "ok": False,
            "summary": {"rows": 0, "errors": 1, "warnings": 0},
            "errors": [x for x in issues if x["level"] == "error"],
            "warnings": [],
        }

    for idx, row in enumerate(rows, start=1):
        excel_row = idx + 1  # header row is row 1 in Excel
        username = _norm((row or {}).get("username"))

        ok_u, reason_u = _username_valid(username)
        if not ok_u:
            issues.append(_issue(
                excel_row,
                username,
                "error",
                "missing_or_invalid_username",
                "Username is missing or invalid.",
                detail=reason_u,
            ))

        if username:
            seen.setdefault(username, []).append(excel_row)

        password = _norm((row or {}).get("password"))
        if password:
            ok_p, reason_p = _password_strong(password)
            if not ok_p:
                issues.append(_issue(
                    excel_row,
                    username,
                    "error",
                    "password_too_weak",
                    "Password is too weak.",
                    detail="Must be at least 15 characters and include uppercase, lowercase, digit, and special character. " + str(reason_p),
                ))
        else:
            issues.append(_issue(
                excel_row,
                username,
                "warning",
                "password_will_be_generated",
                "Password is blank; a compliant password will be generated.",
            ))

        groups = _group_list_from_row(row or {})
        if not groups:
            issues.append(_issue(
                excel_row,
                username,
                "warning",
                "no_groups",
                "No groups provided for this user.",
            ))

        is_admin_raw = _norm((row or {}).get("is_admin", (row or {}).get("admin", "")))
        if is_admin_raw and is_admin_raw.lower() not in ("1", "0", "true", "false", "yes", "no", "y", "n", "on", "off", "admin"):
            issues.append(_issue(
                excel_row,
                username,
                "warning",
                "is_admin_unusual_value",
                "is_admin has an unusual value.",
                detail=f"value={is_admin_raw}",
            ))

    for username, rownums in seen.items():
        if len(rownums) > 1:
            for rn in rownums:
                issues.append(_issue(
                    rn,
                    username,
                    "error",
                    "duplicate_username_in_file",
                    "Username appears more than once in the import file.",
                    detail="rows=" + ",".join(str(x) for x in rownums),
                ))

    errors = [x for x in issues if x["level"] == "error"]
    warnings = [x for x in issues if x["level"] == "warning"]

    return {
        "ok": len(errors) == 0,
        "summary": {
            "rows": len(rows),
            "errors": len(errors),
            "warnings": len(warnings),
        },
        "errors": errors,
        "warnings": warnings,
        "meta": {
            "validator": "static",
            "tak_server_required": False,
        },
    }
