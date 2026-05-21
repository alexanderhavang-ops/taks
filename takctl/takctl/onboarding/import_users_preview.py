from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from takctl.onboarding.import_user_fields import derive_username, map_headers


def as_bool(v: Any) -> bool:
    s = str(v or "").strip().lower()
    if s in ("1", "true", "yes", "y", "on", "admin"):
        return True
    if s in ("0", "false", "no", "n", "off", ""):
        return False
    return True


def read_rows(file_path: Path, limit: int = 50) -> List[List[Any]]:
    suf = file_path.suffix.lower()
    if suf == ".csv":
        import csv
        with file_path.open("r", encoding="utf-8-sig", newline="") as f:
            r = csv.reader(f)
            return [row for _, row in zip(range(limit), r)]

    if suf in (".xlsx", ".xlsm", ".xltx", ".xltm"):
        import openpyxl
        wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
        ws = wb.active
        rows: List[List[Any]] = []
        for row in ws.iter_rows(values_only=True):
            rows.append([("" if v is None else v) for v in row])
            if len(rows) >= limit:
                break
        return rows

    raise RuntimeError(f"unsupported file type: {suf}")


def build_user_from_row(row: List[Any], mapping: Dict[int, str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "username": "",
        "email": "",
        "first_name": "",
        "last_name": "",
        "callsign": "",
        "password": "",
        "is_admin": False,
        "groups": [],
    }

    for idx, field in mapping.items():
        if idx >= len(row):
            continue

        v = row[idx]
        text = "" if v is None else str(v).strip()

        if field in ("username", "email", "first_name", "last_name", "callsign"):
            out[field] = text
        elif field == "password":
            out["password"] = "" if v is None else str(v)
        elif field == "is_admin":
            out["is_admin"] = as_bool(v)
        elif field == "groups":
            sep = ";" if ";" in text else ","
            out["groups"].extend([x.strip() for x in text.split(sep) if x and x.strip()])
        elif field in ("group1", "group2", "group3"):
            if text:
                out["groups"].append(text)

    if not out.get("username"):
        out["username"] = derive_username({"email": out.get("email", "")})

    seen = set()
    out["groups"] = [g for g in out["groups"] if not (g in seen or seen.add(g))]
    return out


def preview_import(file_path: str | Path, sample_n: int = 8) -> Dict[str, Any]:
    p = Path(file_path).expanduser()
    if not p.exists():
        raise RuntimeError(f"file not found: {p}")

    rows = read_rows(p, limit=max(2, sample_n + 1))
    if not rows:
        raise RuntimeError("file is empty")

    headers = [str(h or "").strip() for h in rows[0]]
    mapping, unmapped, normed = map_headers(headers)

    mapped_fields = set(mapping.values())
    missing_required = [] if ("username" in mapped_fields or "email" in mapped_fields) else ["username_or_email"]

    sample_users: List[Dict[str, Any]] = []
    for r in rows[1:1 + sample_n]:
        u = build_user_from_row(r, mapping)
        u["_row_ok"] = bool(u.get("username"))
        sample_users.append(u)

    return {
        "file": str(p),
        "headers": headers,
        "headers_norm": normed,
        "mapping": {str(k): v for k, v in mapping.items()},
        "unmapped_headers": unmapped,
        "missing_required": missing_required,
        "sample_users": sample_users,
    }
