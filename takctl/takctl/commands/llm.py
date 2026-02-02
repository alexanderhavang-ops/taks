from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel

from takctl.appctx import AppContext
from takctl.infra.jsonout import print_json
from takctl.services.llm import llm_status

console = Console()

llm_app = typer.Typer(help="LLM utilities and LLM-backed views (local or remote).")


def _print_status(ctx: typer.Context) -> None:
    appctx: AppContext = ctx.obj["appctx"]
    s = llm_status(appctx)

    if ctx.obj.get("json"):
        print_json(console, s)
        return

    enabled = bool(s.get("enabled", True))
    url = s.get("url", "")
    unit = s.get("unit", "llm-local")

    if not enabled:
        console.print("[yellow]LLM disabled[/yellow]")
        console.print(f"url: {url}")
        console.print(f"unit: {unit}")
        return

    h = s.get("health") or {}
    sd = s.get("systemd") or {}

    ok = bool(h.get("ok", False))
    ok_str = "OK" if ok else "NOT OK"

    payload_present = bool(s.get("local_payload_present", True))
    probed = bool(h.get("probed", False))

    lines: list[str] = []
    lines.append(f"url: {url}")
    lines.append(f"unit: {unit}")
    lines.append(f"payload: {'present' if payload_present else 'missing'}")
    lines.append(f"probed: {probed}")
    lines.append("")
    lines.append(f"health: {ok_str}")

    if "status_code" in h:
        lines.append(f"http: {h.get('status_code')}")
    if h.get("error"):
        lines.append(f"error: {h.get('error')}")

    body = h.get("body")
    if body:
        body = str(body)
        if len(body) > 200:
            body = body[:200] + "…"
        lines.append(f"body: {body}")

    if sd:
        lines.append("")
        active = sd.get("active")
        sub = sd.get("sub")
        descr = sd.get("description")
        if active is not None or sub is not None:
            lines.append(f"systemd: {active}/{sub}")
        if descr:
            lines.append(f"desc: {descr}")
        if sd.get("error"):
            lines.append(f"systemd_error: {sd.get('error')}")

    console.print(Panel("\n".join(lines), title="LLM status", expand=False))


@llm_app.command("status")
def status_cmd(ctx: typer.Context) -> None:
    """Show local/remote LLM connectivity and systemd status."""
    _print_status(ctx)


def _view_stub(ctx: typer.Context, name: str) -> None:
    """
    Placeholder for the future LLM views. We intentionally keep the command surface
    stable while implementation is deferred.
    """
    appctx: AppContext = ctx.obj["appctx"]
    s = llm_status(appctx)

    if ctx.obj.get("json"):
        out = {
            "view": name,
            "llm": s,
            "implemented": False,
            "message": "Not implemented yet. This is a placeholder view.",
        }
        print_json(console, out)
        return

    console.print(
        Panel(
            "\n".join(
                [
                    f"view: {name}",
                    "status: not implemented",
                    "",
                    "This command is a placeholder for the planned takctl LLM views.",
                    "Implementation will summarize TAK data and node state via local/remote LLM.",
                    "",
                    "Tip: run `takctl llm status` to see whether an LLM endpoint is reachable.",
                ]
            ),
            title=f"LLM view: {name}",
            expand=False,
        )
    )

    console.print("")
    _print_status(ctx)


@llm_app.command("tactical")
def tactical_cmd(ctx: typer.Context) -> None:
    """Tactical Operations view (planned)."""
    _view_stub(ctx, "tactical-operations")


@llm_app.command("opsec")
def opsec_cmd(ctx: typer.Context) -> None:
    """Operational Security view (planned)."""
    _view_stub(ctx, "operational-security")


@llm_app.command("health")
def health_cmd(ctx: typer.Context) -> None:
    """System Health view (planned)."""
    _view_stub(ctx, "system-health")


def register(app: typer.Typer) -> None:
    # Proper subcommands: `takctl llm status|tactical|opsec|health`
    app.add_typer(llm_app, name="llm")

    @app.command("llm")
    def llm_legacy(
        ctx: typer.Context,
        status: bool = typer.Option(True, "--status/--no-status", help="Show LLM status"),
    ) -> None:
        """
        Backwards compatible entrypoint.

        Prefer: `takctl llm status`
        """
        if not status:
            console.print("[yellow]Nothing to do (use --status)[/yellow]")
            raise typer.Exit(0)
        _print_status(ctx)

