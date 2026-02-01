from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel

from takctl.appctx import AppContext
from takctl.infra.jsonout import print_json
from takctl.services.llm import llm_status

console = Console()


def register(app: typer.Typer) -> None:
    @app.command("llm")
    def llm(
        ctx: typer.Context,
        status: bool = typer.Option(True, "--status/--no-status", help="Show LLM status"),
    ):
        """
        LLM utilities (local or remote llama-server).
        """
        appctx: AppContext = ctx.obj["appctx"]
        s = llm_status(appctx)

        if ctx.obj.get("json"):
            print_json(console, s)
            return

        if not s.get("enabled", True):
            console.print("[yellow]LLM disabled[/yellow]")
            console.print(f"url: {s.get(\"url\",\"\")}")
            console.print(f"unit: {s.get(\"unit\",\"llm-local\")}")
            return

        h = s.get("health", {})
        sd = s.get("systemd", {})

        lines = []
        lines.append(f"url: {s.get(\"url\")}")
        lines.append(f"unit: {s.get(\"unit\")}")
        lines.append("")
        lines.append(f"health: {OK if h.get(ok) else NOT
