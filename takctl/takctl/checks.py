from __future__ import annotations

from pathlib import Path

from rich.console import Console

from takctl.appctx import AppContext
from takctl.domain.errors import TakctlAssumptionError

console = Console()


def run_startup_checks(ctx: AppContext, verbose: bool = False) -> None:
    """
    Run quick, safe checks so failures are obvious early.
    Keep these checks re-usable for a future web /health endpoint.
    """
    _check_paths(ctx)
    _check_db(ctx)
    _check_openssl(ctx)

    if verbose:
        console.print(
            f"[dim]DB backend: {ctx.cfg.db_mode} (db={ctx.cfg.db_name}, user={ctx.cfg.db_user})[/dim]"
        )


def _check_paths(ctx: AppContext) -> None:
    core = Path(ctx.cfg.coreconfig_path)
    if not core.exists():
        raise TakctlAssumptionError(f"CoreConfig not found: {core}")

    crl = Path(ctx.cfg.crl_path)
    if not crl.exists():
        # CRL might be optional depending on deployment, but your workflow expects it.
        # We warn, not fail.
        console.print(f"[yellow]WARN[/yellow] CRL file not found: {crl}")

    ca = Path(ctx.cfg.ca_dir)
    if not ca.exists():
        console.print(f"[yellow]WARN[/yellow] CA dir not found: {ca}")


def _check_db(ctx: AppContext) -> None:
    # light ping query
    try:
        ctx.db.scalar("SELECT 1;")
    except Exception as e:
        raise TakctlAssumptionError(f"DB access failed using mode={ctx.cfg.db_mode}: {e}") from e


def _check_openssl(ctx: AppContext) -> None:
    try:
        ctx.openssl.version()
    except Exception as e:
        raise TakctlAssumptionError(f"openssl not usable: {e}") from e

