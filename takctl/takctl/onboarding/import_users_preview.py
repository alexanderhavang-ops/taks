from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

KNOWN: Dict[str, List[str]] = {
    "username": ["username","user","name","login"],
    "password": ["password","pass","pw"],
    "is_admin": ["is_admin","admin","administrator","taks_admin","marti_admin"],
    "group1": ["group1","group_1","group_a","group_primary","grp1"],
    "group2": ["group2","group_2","group_b","group_secondary","grp2"],
    "group3": ["group3","group_3","group_c","group_tertiary","grp3"],
}

def _norm(s: Any) -> str:
    t = str(s or "").strip().lower()
    out = []
    for ch in t:
        if ch.isalnum() or ch in ("_","-"," "):
            out.append(ch)
    return "".join(out).replace(" ", "_").replace("-", "_")

def as_bool(v: Any) -> bool:
    s = str(v or "").strip().lower()
    if s in ("1","true","yes","y","on","admin"):
        return True
    if s in ("0","false","no","n","off",""):
        return False
    return True

def map_headers(headers: List[str]) -> Tuple[Dict[int,str], List[str], List[str]]:
    normed = [_norm(h) for h in headers]
    mapping: Dict[int,str] = {}
    unmapped: List[str] = []
    used = set()

    for i, h in enumerate(normed):
        field = None
        for k, aliases in KNOWN.items():
            if h == k or h in aliases:
                field = k
                break
        if field and field not in used:
            mapping[i] = field
            used.add(field)
        else:
            unmapped.append(headers[i])
    return mapping, unmapped, normed

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

def build_user_from_row(row: List[Any], mapping: Dict[int,str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"username":"", "password":"", "is_admin": False, "groups":[]}
    for idx, field in mapping.items():
        if idx >= len(row):
            continue
        v = row[idx]
        if field == "username":
            out["username"] = str(v or "").strip()
        elif field == "password":
            out["password"] = "" if v is None else str(v)
        elif field == "is_admin":
            out["is_admin"] = as_bool(v)
        elif field in ("group1","group2","group3"):
            g = str(v or "").strip()
            if g:
                out["groups"].append(g)

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
    missing_required = [r for r in ("username",) if r not in mapping.values()]

    sample_users: List[Dict[str, Any]] = []
    for r in rows[1:1+sample_n]:
        u = build_user_from_row(r, mapping)
        u["_row_ok"] = bool(u.get("username"))
        sample_users.append(u)

    return {
        "file": str(p),
        "headers": headers,
        "headers_norm": normed,
        "mapping": {str(k): v for k,v in mapping.items()},
        "unmapped_headers": unmapped,
        "missing_required": missing_required,
        "sample_users": sample_users,
    }
