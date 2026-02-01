# --- imports near the top (adjust to match your file structure) ---
from fastapi import Depends, FastAPI, HTTPException, Query
from pathlib import Path

from takctl.services.userauth_file import (
    UserAuthFileError,
    auth_file_path,
    get_user_auth_record,
    list_users as list_auth_users,
)

# ... keep your app / ctx stuff ...


@app.get("/api/users/_debug")
def users_debug(ctx: AppContext = Depends(get_ctx)) -> dict:
    """
    Debug endpoint to show how we resolve UserAuthenticationFile.xml from CoreConfig.xml.
    Safe to leave in; doesn't leak secrets beyond paths + readability.
    """
    core = Path(ctx.cfg.coreconfig_path)
    out = {
        "coreconfig_path": str(core),
        "coreconfig_exists": core.exists(),
        "coreconfig_abs": str(core.resolve()) if core.exists() else str(core),
        "coreconfig_dir": str(core.parent),
        "parse_ok": None,
        "found_auth": None,
        "found_file_under_auth": None,
        "file_location_raw": None,
        "resolved_auth_xml": None,
        "auth_xml_exists": None,
        "auth_xml_readable": None,
        "notes": [],
    }

    # Use auth_file_path() as the source of truth for parsing CoreConfig.xml
    try:
        p = auth_file_path(str(core))
        out["resolved_auth_xml"] = p
        out["auth_xml_exists"] = Path(p).exists()
        out["auth_xml_readable"] = os.access(p, os.R_OK)

        # If auth_file_path() succeeded, parsing + auth/file lookup must have worked
        out["parse_ok"] = True
        out["found_auth"] = True
        out["found_file_under_auth"] = True
        # we don't have the raw attribute easily without duplicating parser internals
        out["file_location_raw"] = "(resolved via auth_file_path)"
    except Exception as e:
        out["notes"].append(str(e))
        out["parse_ok"] = False
        out["found_auth"] = False
        out["found_file_under_auth"] = False

    return out


def _guard_coreconfig_path(coreconfig_path: str) -> None:
    # Prevent the exact bug we hit: passing the auth XML path where CoreConfig.xml is expected.
    p = coreconfig_path.lower()
    if p.endswith("userauthenticationfile.xml"):
        raise HTTPException(
            status_code=500,
            detail=(
                "Config error: expected cfg.coreconfig_path to be CoreConfig.xml, "
                f"but it points at UserAuthenticationFile.xml: {coreconfig_path}"
            ),
        )


@app.get("/api/users")
def users_api(ctx: AppContext = Depends(get_ctx)) -> dict:
    try:
        _guard_coreconfig_path(ctx.cfg.coreconfig_path)

        rows = list_auth_users(ctx.cfg.coreconfig_path)  # <-- PASS CORECONFIG HERE
        return {
            "count": len(rows),
            "users": [{"username": r.username, "role": r.role} for r in rows],
        }
    except UserAuthFileError as e:
        # Clean + actionable
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Users API failed: {e}")


@app.get("/api/users/{username}")
def user_detail_api(username: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    try:
        _guard_coreconfig_path(ctx.cfg.coreconfig_path)

        r = get_user_auth_record(ctx.cfg.coreconfig_path, username)  # <-- CORECONFIG
        return {
            "username": r.username,
            "role": r.role,
            "fingerprint": r.fingerprint,
            "groups_rw": r.groups_rw,
            "groups_in": r.groups_in,
            "groups_out": r.groups_out,
            "source_path": r.source_path,
        }
    except UserAuthFileError as e:
        msg = str(e)
        if "not found in auth XML" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=500, detail=msg)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"User detail failed: {e}")

