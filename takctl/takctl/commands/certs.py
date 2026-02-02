from __future__ import annotations

import json
import typer
from rich.console import Console
from rich.table import Table

from takctl.appctx import AppContext
from takctl.services.certs import list_all_certs

app = typer.Typer(help="Certificate utilities")
console = Console()


def _get_ctx(ctx: typer.Context) -> AppContext:
    try:
        return ctx.obj["appctx"]
    except Exception:
        raise typer.Exit(code=2)


def _cert_to_dict(c) -> dict:
    expires = getattr(c, "expires", None)
    return {
        "id": getattr(c, "id", None),
        "client_uid": getattr(c, "client_uid", None),
        "subject_dn": getattr(c, "subject_dn", None),
        "expires": expires.isoformat() if expires else None,
        "revoked_in_db": bool(getattr(c, "revoked_in_db", False)),
        "serial_hex": getattr(c, "serial_hex", None),
        "revoked_in_crl": bool(getattr(c, "revoked_in_crl", False)),
    }


@app.command("list")
def cmd_list(
    ctx: typer.Context,
    client_uid: str | None = typer.Option(
        None,
        "--client-uid",
        help="Filter by clientUid. If omitted, lists all certificates.",
    ),
    limit: int = typer.Option(200, "--limit", min=1, max=50000, help="Max rows to return."),
    json_out: bool = typer.Option(False, "--json", help="Output JSON instead of a table."),
):
    """
    List certificates.

    IMPORTANT: This command intentionally does NOT call services.certs.list_certs()
    because that SQL has been observed to fail on some installs.
    We always use list_all_certs() and filter in Python instead.
    """
    appctx = _get_ctx(ctx)

    # Pull enough rows to satisfy filtering + limit.
    # If client_uid is set, we may need more than limit from the DB to find limit matches,
    # but list_all_certs already orders DESC and your dataset is small; keep it simple.
    rows = list_all_certs(appctx, limit=50000 if client_uid else limit)

    if client_uid:
        rows = [c for c in rows if getattr(c, "client_uid", None) == client_uid][:limit]
    else:
        rows = rows[:limit]

    if json_out:
        payload = {"count": len(rows), "certs": [_cert_to_dict(r) for r in rows]}
        console.print(json.dumps(payload, indent=2, default=str))
        raise typer.Exit()

    table = Table(title=f"Certificates ({len(rows)})", show_lines=False)
    table.add_column("id", justify="right", no_wrap=True)
    table.add_column("client_uid", no_wrap=True)
    table.add_column("subject_dn", overflow="fold")
    table.add_column("expires", no_wrap=True)
    table.add_column("db_revoked", justify="center", no_wrap=True)
    table.add_column("serial", no_wrap=True)
    table.add_column("crl_revoked", justify="center", no_wrap=True)

    for c in rows:
        expires = getattr(c, "expires", None)
        table.add_row(
            str(getattr(c, "id", "")),
            str(getattr(c, "client_uid", "") or ""),
            str(getattr(c, "subject_dn", "") or ""),
            expires.isoformat() if expires else "",
            "Y" if getattr(c, "revoked_in_db", False) else "",
            str(getattr(c, "serial_hex", "") or ""),
            "Y" if getattr(c, "revoked_in_crl", False) else "",
        )

    console.print(table)
