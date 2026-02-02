from __future__ import annotations

import typer
from rich.table import Table
from rich.console import Console

from takctl.appctx import AppContext
from takctl.services.clients import list_clients
from takctl.api.schemas import clients_list_response

console = Console()


def register(app: typer.Typer) -> None:
    @app.command("clients")
    def clients(
        ctx: typer.Context,
        limit: int = typer.Option(30, "--limit", help="Max clients to show"),
    ):
        appctx: AppContext = ctx.obj["appctx"]
        rows = list_clients(appctx, limit=limit)

        # JSON mode (aligned with web API schema)
        if ctx.obj.get("json"):
            payload = clients_list_response(rows)
            # print pure JSON (no rich formatting)
            import json
            console.print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return

        # Human mode
        t = Table(title=f"Clients (top {limit})")
        t.add_column("callsign")
        t.add_column("uid")
        t.add_column("last_seen")

        for r in rows:
            t.add_row(r.callsign, r.uid, str(r.last_seen))

        console.print(t)

