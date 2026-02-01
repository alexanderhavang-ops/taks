from __future__ import annotations

import typer
from rich.console import Console

from takctl.services.crl import crl_status, rebuild_crl_from_db

app = typer.Typer(help="CRL utilities")
console = Console()


@app.command("status")
def status(ctx: typer.Context):
    """
    Show CRL path, mtime, and revoked serial count.
    """
    appctx = ctx.obj["appctx"]
    s = crl_status(appctx)

    console.print(f"CRL: {s['crl_path']}")
    if not s["exists"]:
        console.print("mtime: (missing)")
        console.print("revoked serials: 0")
        return

    console.print(f"mtime: {s['mtime']}")
    console.print(f"revoked serials: {s['revoked_serials']}")
    if s["sample_serials"]:
        console.print(f"sample revoked serials: {', '.join(s['sample_serials'][:5])}")


@app.command("rebuild")
def rebuild(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", help="Required: destructive rebuild of OpenSSL CRL DB + CRL"),
):
    """
    Rebuild CRL from Postgres revoked certs.
    """
    if not force:
        raise typer.BadParameter("--force is required (destructive operation)")

    appctx = ctx.obj["appctx"]
    rebuild_crl_from_db(appctx, force=True)
    console.print("[green]OK[/green] CRL rebuilt from Postgres")

