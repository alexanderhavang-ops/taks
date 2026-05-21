from __future__ import annotations

import csv
import secrets
from pathlib import Path
from typing import List, Dict, Any, Callable, Optional

try:
    import openpyxl
except Exception:
    openpyxl = None

from takctl.onboarding.policy import Policy
from takctl.onboarding.selection import save_selection
from takctl.services.backing_user_store import BackingUserStoreError, build_backing_user_store
from takctl.api.onboarding_identity import _issue_card_link_base
from takctl.config import load_config
from takctl.onboarding.import_user_fields import canonicalize_row, derive_username


# ------------------------------------------------------------
# file readers
# ------------------------------------------------------------

def _read_csv(path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []

    with path.open("r", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(canonicalize_row(dict(row or {})))

    return rows


def _read_xlsx(path: Path) -> List[Dict[str, str]]:
    if openpyxl is None:
        raise RuntimeError("openpyxl not installed")

    wb = openpyxl.load_workbook(path)
    ws = wb.active

    header: List[str] = []
    rows: List[Dict[str, str]] = []

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            header = [(str(c).strip() if c is not None else "") for c in row]
            continue

        raw: Dict[str, str] = {}
        for k, v in zip(header, row):
            if not k:
                continue
            raw[k] = (str(v).strip() if v is not None else "")

        rows.append(canonicalize_row(raw))

    return rows


def load_file(path: str) -> List[Dict[str, str]]:
    p = Path(path)

    if not p.exists():
        raise RuntimeError(f"file not found: {path}")

    if p.suffix.lower() == ".csv":
        return _read_csv(p)

    if p.suffix.lower() in (".xlsx", ".xlsm"):
        return _read_xlsx(p)

    raise RuntimeError(f"unsupported file type: {p.suffix}")


# ------------------------------------------------------------
# helpers
# ------------------------------------------------------------

def _bool(v: str) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on", "admin")


def _group_list_from_row(row: Dict[str, str]) -> List[str]:
    """
    Preferred v1 schema:
      group1, group2, group3

    Back-compat:
      groups = "A;B;C" or "A,B,C"
    """
    out: List[str] = []

    for k in ("group1", "group2", "group3"):
        v = (row.get(k) or "").strip()
        if v:
            out.append(v)

    if not out:
        raw = (row.get("groups") or "").strip()
        if raw:
            sep = ";" if ";" in raw else ","
            out = [x.strip() for x in raw.split(sep) if x and x.strip()]

    seen = set()
    final: List[str] = []
    for g in out:
        if g not in seen:
            seen.add(g)
            final.append(g)
    return final


def _gen_strong_password(length: int = 20) -> str:
    """
    Marti/UserManager-compatible:
      - min 15 chars
      - uppercase, lowercase, digit, special
    """
    specials = r"-_!@#$%^&*(){}[]+=~`|:;<>,./?"
    uppers = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    lowers = "abcdefghijklmnopqrstuvwxyz"
    digits = "0123456789"

    n = max(int(length), 15)

    chars = [
        secrets.choice(uppers),
        secrets.choice(lowers),
        secrets.choice(digits),
        secrets.choice(specials),
    ]

    alphabet = uppers + lowers + digits + specials
    while len(chars) < n:
        chars.append(secrets.choice(alphabet))

    for i in range(len(chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]

    return "".join(chars)


def _ctx_from_row(row: Dict[str, str]) -> Dict[str, Any]:
    """
    Keep this permissive. Minimal imports only need username/groups/admin,
    but we allow future-friendly optional identity columns too.
    """
    ctx: Dict[str, Any] = {}

    for k in (
        "policy_id",
        "battalion",
        "battalion_fal",
        "company",
        "platoon",
        "group",
        "n",
        "team",
        "callsign",
        "callsign_policy",
        "role",
        "remarks",
        "email",
    ):
        v = (row.get(k) or "").strip()
        if v:
            ctx[k] = v

    if "policy_id" not in ctx:
        from takctl.onboarding.policy_registry import default_policy_id
        ctx["policy_id"] = default_policy_id()

    return ctx


# ------------------------------------------------------------
# validation
# ------------------------------------------------------------

IDENTITY_FIELDS = ["company", "platoon", "group", "n"]


def validate_rows(rows: List[Dict[str, str]]) -> None:
    if not rows:
        raise RuntimeError("import file is empty")

    first = rows[0]

    if "username" not in first and "email" not in first and not all(x in first for x in IDENTITY_FIELDS):
        raise RuntimeError(
            "file must contain either 'username', 'email', or identity columns "
            "(company, platoon, group, n)"
        )


# ------------------------------------------------------------
# row apply
# ------------------------------------------------------------

def _apply_row(
    service,
    row: Dict[str, str],
    *,
    update_existing: bool,
) -> Dict[str, Any]:
    email = (row.get("email") or "").strip()
    username = (row.get("username") or "").strip() or derive_username(row)
    if not username:
        raise RuntimeError("username or email is required in import")

    row = dict(row)
    row["username"] = username

    ctx = _ctx_from_row(row)
    ctx["username"] = username

    password_in = (row.get("password") or "").strip()
    email = (row.get("email") or "").strip()
    admin = _bool(row.get("is_admin", row.get("admin", "")))
    groups = _group_list_from_row(row)

    existing_user = service.ud.get_user(username)
    if existing_user is not None and not update_existing:
        return {"status": "skipped", "username": username, "reason": "exists"}

    password_to_set = None
    password_source = "unchanged"

    if existing_user is None:
        if password_in:
            password_to_set = password_in
            password_source = "provided"
        else:
            password_to_set = _gen_strong_password(20)
            password_source = "generated"
    else:
        if password_in:
            password_to_set = password_in
            password_source = "provided"
        else:
            password_to_set = None
            password_source = "unchanged"

    writer = build_backing_user_store(getattr(service, "backing_user_store", None))
    try:
        writer.ensure_user(
            username,
            password=password_to_set,
            admin=True if admin else None,
            groups=groups,
            in_groups=[],
            out_groups=[],
            append=False,
            remove=False,
            ctx=ctx,
        )
    except BackingUserStoreError as e:
        raise RuntimeError(f"user store write failed: {e}")

    tak_user = service.ud.get_user(username)
    if tak_user is None:
        raise RuntimeError(f"user not found after create/update in configured backing user store: {username}")

    from takctl.onboarding.policy_registry import default_policy_id
    default_pid = default_policy_id()
    policy_id = str(ctx.get("policy_id") or default_pid).strip() or default_pid
    ident_out: Dict[str, Any] = {}
    try:
        pol = Policy(policy_id=policy_id)
        ident = pol.resolve_identity(ctx)
        ident_out = {
            "callsign": getattr(ident, "callsign", None),
            "team": getattr(ident, "team", None),
            "atak_role_type": getattr(ident, "atak_role_type", None),
        }
        v = getattr(ident, "callsign_variants", None)
        if isinstance(v, dict) and v:
            ident_out["callsign_variants"] = v
        eff = getattr(ident, "callsign_policy_effective", None)
        if eff:
            ident_out["callsign_policy_effective"] = eff
    except Exception as e:
        ctx = dict(ctx)
        ctx.setdefault("_policy_error", str(e))

    identity_rec = service.store.upsert_identity(
        username=username,
        origin="taks",
        ctx=ctx,
        identity=ident_out,
        password=password_to_set,
    )

    selection = {
        "ctx": ctx,
        "paths": {"B": True, "itak": True, "wintak": True},
        "endpoints": {},
    }
    save_selection(username, selection)

    xmpp_bookmarks = None
    try:
        from takctl.onboarding.xmpp_bookmarks import enqueue_user_bookmarks

        xmpp_bookmarks = enqueue_user_bookmarks(
            username=username,
            password=password_to_set or getattr(identity_rec, "password", None),
            selection=selection,
            identity=ident_out,
            reason="import_users",
        )
    except Exception as e:
        xmpp_bookmarks = {"ok": False, "queued": False, "error": f"{type(e).__name__}: {e}"}

    # Generate soldier card link for this user
    card_url = None
    try:
        base = getattr(service, "external_base", None) or ""
        if base:
            card_info = _issue_card_link_base(
                base,
                service,
                username=username,
                reveal_password=True,
            )
            card_url = card_info.get("card_url")
    except Exception:
        card_url = None

    return {
        "status": "updated" if existing_user is not None else "created",
        "username": username,
        "email": email or None,
        "password_set": bool(password_to_set),
        "password_generated": password_source == "generated",
        "password_source": password_source,
        "groups": groups,
        "admin": bool(admin),
        "card_url": card_url,
        "xmpp_bookmarks": xmpp_bookmarks,
    }


# ------------------------------------------------------------
# importer
# ------------------------------------------------------------

ProgressCb = Optional[Callable[[Dict[str, Any]], None]]


def _emit_progress(progress_cb: ProgressCb, payload: Dict[str, Any]) -> None:
    if progress_cb is None:
        return
    try:
        progress_cb(payload)
    except Exception:
        pass


def import_users(
    service,
    rows: List[Dict[str, str]],
    *,
    dry_run: bool = False,
    update_existing: bool = False,
    progress_cb: ProgressCb = None,
) -> Dict[str, Any]:

    created = 0
    updated = 0
    skipped = 0
    errors: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    total_rows = len(rows)

    for i, row in enumerate(rows, start=1):
        username = (row.get("username") or "").strip()
        password_in = (row.get("password") or "").strip()
        email = (row.get("email") or "").strip()

        try:
            exists = bool(username and service.ud.get_user(username) is not None)

            if exists and not update_existing:
                skipped += 1
                item = {
                    "row": i,
                    "status": "skipped",
                    "username": username,
                    "reason": "exists",
                    "email": email or None,
                    "password_set": False,
                    "password_generated": False,
                    "password_source": "unchanged",
                }
                results.append(item)
                _emit_progress(progress_cb, {
                    "row": i,
                    "total_rows": total_rows,
                    "username": username,
                    "status": "skipped",
                    "created": created,
                    "updated": updated,
                    "skipped": skipped,
                    "error_count": len(errors),
                })
                continue

            if dry_run:
                st = "updated" if exists else "created"
                if exists:
                    updated += 1
                    password_source = "provided" if password_in else "unchanged"
                    password_set = bool(password_in)
                    password_generated = False
                else:
                    created += 1
                    password_source = "provided" if password_in else "generated"
                    password_set = True
                    password_generated = not bool(password_in)

                item = {
                    "row": i,
                    "status": st,
                    "username": username,
                    "email": email or None,
                    "admin": _bool(row.get("is_admin", row.get("admin", ""))),
                    "groups": _group_list_from_row(row),
                    "password_set": password_set,
                    "password_generated": password_generated,
                    "password_source": password_source,
                }
                results.append(item)
                _emit_progress(progress_cb, {
                    "row": i,
                    "total_rows": total_rows,
                    "username": username,
                    "status": st,
                    "created": created,
                    "updated": updated,
                    "skipped": skipped,
                    "error_count": len(errors),
                })
                continue

            res = _apply_row(service, row, update_existing=update_existing)
            results.append({"row": i, **res})

            if res["status"] == "created":
                created += 1
            elif res["status"] == "updated":
                updated += 1
            elif res["status"] == "skipped":
                skipped += 1

            _emit_progress(progress_cb, {
                "row": i,
                "total_rows": total_rows,
                "username": username or res.get("username"),
                "status": res.get("status"),
                "created": created,
                "updated": updated,
                "skipped": skipped,
                "error_count": len(errors),
            })

        except Exception as e:
            errors.append({
                "row": i,
                "error": str(e),
                "data": row,
            })
            _emit_progress(progress_cb, {
                "row": i,
                "total_rows": total_rows,
                "username": username,
                "status": "error",
                "error": str(e),
                "created": created,
                "updated": updated,
                "skipped": skipped,
                "error_count": len(errors),
            })

    return {
        "rows": len(rows),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "results": results,
    }


# ------------------------------------------------------------
# entrypoint
# ------------------------------------------------------------

def run_import(service, path: str, *, dry_run=False, update_existing=False, progress_cb: ProgressCb = None):
    rows = load_file(path)
    validate_rows(rows)
    return import_users(
        service,
        rows,
        dry_run=dry_run,
        update_existing=update_existing,
        progress_cb=progress_cb,
    )
