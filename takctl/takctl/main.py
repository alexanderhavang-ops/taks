from __future__ import annotations

import importlib
import pkgutil

import typer
from rich.console import Console

from takctl.config import load_config
from takctl.appctx import build_context

console = Console()

app = typer.Typer(
    add_completion=False,
    help="takctl - TAK control CLI",
)


def _load_commands(app: typer.Typer) -> None:
    import takctl.commands as commands_pkg

    for m in pkgutil.iter_modules(commands_pkg.__path__):
        if m.ispkg:
            continue

        modname = f"takctl.commands.{m.name}"
        try:
            mod = importlib.import_module(modname)
        except Exception as e:
            console.print(f"[yellow]Skipping {modname} (import error):[/yellow] {e}")
            continue

        # Preferred pattern: register(app)
        reg = getattr(mod, "register", None)
        if callable(reg):
            try:
                reg(app)
            except Exception as e:
                console.print(f"[yellow]Skipping {modname} (register error):[/yellow] {e}")
            continue

        # Fallback: module-level Typer app
        sub = getattr(mod, "app", None)
        if sub is not None:
            try:
                app.add_typer(sub, name=m.name.replace("_", "-"))
            except Exception as e:
                console.print(f"[yellow]Skipping {modname} (add_typer error):[/yellow] {e}")


# IMPORTANT: load commands before Typer parses argv
_load_commands(app)


@app.callback()
def _root(
    ctx: typer.Context,
    json: bool = typer.Option(
        False,
        "--json",
        help="Output machine-readable JSON instead of formatted text",
    ),
) -> None:
    """
    Root entrypoint. Build AppContext and attach it to Typer context.
    """
    cfg = load_config()
    ctx.obj = {
        "appctx": build_context(cfg),
        "json": json,
    }


def entrypoint() -> None:
    app()


if __name__ == "__main__":
    entrypoint()

