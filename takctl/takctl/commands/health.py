from __future__ import annotations

import typer
from rich.console import Console

from takctl.appctx import AppContext
from takctl.checks import run_startup_checks

console = Console()


def register(app: typer.Typer) -> None:
    @app.command("health")
    def health(
        ctx: typer.Context,
        verbose: bool = typer.Option(False, "--verbose", "-v"),
    ):
        """
        Re-run startup checks on-demand (useful for future web /health mapping).
        """
        appctx: AppContext = ctx.obj["appctx"]
        run_startup_checks(appctx, verbose=verbose)
        console.print("[green]OK[/green] health checks passed.")
