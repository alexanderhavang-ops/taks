from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from takctl.services.usermgr import UserMgrService, UserMgrError

console = Console()
app = typer.Typer(help="Manage TAK users via UserManager.jar (writes) + auth XML (reads)")

cert_app = typer.Typer(help="Manage certificate-based users via UserManager.jar")
app.add_typer(cert_app, name="cert")


@app.command("auth-path")
def auth_path(ctx: typer.Context) -> None:
    """
    Show which UserAuthentication XML file takctl resolved from CoreConfig.xml.
    """
    appctx = ctx.obj["appctx"]
    try:
        from takctl.services.userauth_file import auth_file_path
        p = auth_file_path(appctx.cfg.coreconfig_path)
        console.print(p)
    except Exception as e:
        console.print(Panel.fit(str(e), title="ERROR", border_style="red"))
        raise typer.Exit(1)


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show role/fingerprint + group counts"),
) -> None:
    """
    List users from the UserAuthentication XML (read-only).
    """
    appctx = ctx.obj["appctx"]
    try:
        from takctl.services.userauth_file import list_users
        users = list_users(appctx.cfg.coreconfig_path)

        t = Table(title=f"Users ({len(users)})")
        t.add_column("username")
        if verbose:
            t.add_column("role")
            t.add_column("fingerprint")
            t.add_column("rw")
            t.add_column("in")
            t.add_column("out")

        for u in users:
            if verbose:
                t.add_row(
                    u.username,
                    u.role or "",
                    (u.fingerprint or "")[:16] + ("…" if u.fingerprint and len(u.fingerprint) > 16 else ""),
                    str(len(u.groups_rw)),
                    str(len(u.groups_in)),
                    str(len(u.groups_out)),
                )
            else:
                t.add_row(u.username)

        console.print(t)
    except Exception as e:
        console.print(Panel.fit(str(e), title="ERROR", border_style="red"))
        raise typer.Exit(1)


@app.command("status")
def status(
    ctx: typer.Context,
    username: str = typer.Argument(..., help="TAK username"),
):
    """
    Show status for a TAK user (read-only from auth XML).
    """
    appctx = ctx.obj["appctx"]
    try:
        from takctl.services.userauth_file import get_user_auth_record
        rec = get_user_auth_record(appctx.cfg.coreconfig_path, username)

        lines: list[str] = []
        lines.append(f"Username:      '{rec.username}'")
        if rec.role:
            lines.append(f"Role:          {rec.role}")
        if rec.fingerprint:
            lines.append(f"Fingerprint:   {rec.fingerprint}")

        if rec.groups_rw:
            lines.append("Groups (read/write):")
            for g in rec.groups_rw:
                lines.append(f"  {g}")
        if rec.groups_in:
            lines.append("Groups (in/write-only):")
            for g in rec.groups_in:
                lines.append(f"  {g}")
        if rec.groups_out:
            lines.append("Groups (out/read-only):")
            for g in rec.groups_out:
                lines.append(f"  {g}")

        lines.append(f"[dim]Source: {rec.source_path}[/dim]")
        console.print(Panel.fit("\n".join(lines), title=f"user: {username}", border_style="green"))
    except Exception as e:
        console.print(Panel.fit(str(e), title="ERROR", border_style="red"))
        raise typer.Exit(1)


@app.command("set")
def set_user(
    ctx: typer.Context,
    username: str = typer.Argument(..., help="TAK username"),
    password: str | None = typer.Option(None, "--password", "-p", help="Set user password"),
    admin: bool = typer.Option(False, "--admin", help="Grant administrator role"),
    fingerprint: str | None = typer.Option(None, "--fingerprint", "-f", help="Set fingerprint for user auth"),
    certificate: str | None = typer.Option(None, "--certificate", "-c", help="Certificate path to derive fingerprint"),
    group: list[str] | None = typer.Option(None, "--group", "-g", help="Read/write group (repeatable)"),
    in_group: list[str] | None = typer.Option(None, "--in-group", "-ig", help="Write-only group (repeatable)"),
    out_group: list[str] | None = typer.Option(None, "--out-group", "-og", help="Read-only group (repeatable)"),
    append: bool = typer.Option(False, "--append", "-a", help="Append groups instead of replacing"),
    remove: bool = typer.Option(False, "--remove", "-r", help="Remove specified groups"),
):
    """
    Create or modify a TAK user (WRITE via UserManager.jar).
    """
    svc = UserMgrService()
    try:
        out = svc.user_set(
            username=username,
            password=password,
            admin=admin if admin else None,
            fingerprint=fingerprint,
            certificate_path=certificate,
            groups=group,
            in_groups=in_group,
            out_groups=out_group,
            append=append,
            remove=remove,
        )
        console.print(Panel.fit(out or "OK", title=f"user updated: {username}", border_style="green"))
    except UserMgrError as e:
        console.print(Panel.fit(str(e), title="ERROR", border_style="red"))
        raise typer.Exit(1)


@app.command("delete")
def delete(
    ctx: typer.Context,
    username: str = typer.Argument(..., help="TAK username"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """
    Delete a TAK user (WRITE via UserManager.jar).
    """
    if not yes:
        typer.confirm(f"Delete user '{username}'?", abort=True)

    svc = UserMgrService()
    try:
        out = svc.user_delete(username)
        console.print(Panel.fit(out or "OK", title=f"user deleted: {username}", border_style="yellow"))
    except UserMgrError as e:
        console.print(Panel.fit(str(e), title="ERROR", border_style="red"))
        raise typer.Exit(1)


# --------------------
# certmod subtree (write via jar)
# --------------------

@cert_app.command("status")
def cert_status(
    ctx: typer.Context,
    cert_path: str = typer.Argument(..., help="Path to certificate (PEM)"),
):
    svc = UserMgrService()
    try:
        st = svc.cert_status(cert_path)
        console.print(Panel.fit(st.raw, title=f"cert: {cert_path}", border_style="green"))
    except UserMgrError as e:
        console.print(Panel.fit(str(e), title="ERROR", border_style="red"))
        raise typer.Exit(1)


@cert_app.command("set")
def cert_set(
    ctx: typer.Context,
    cert_path: str = typer.Argument(..., help="Path to certificate (PEM)"),
    password: str | None = typer.Option(None, "--password", "-p", help="Set password for cert-based user"),
    admin: bool = typer.Option(False, "--admin", help="Grant administrator role"),
    fingerprint: str | None = typer.Option(None, "--fingerprint", "-f", help="Override certificate fingerprint"),
    group: list[str] | None = typer.Option(None, "--group", "-g", help="Read/write group (repeatable)"),
    in_group: list[str] | None = typer.Option(None, "--in-group", "-ig", help="Write-only group (repeatable)"),
    out_group: list[str] | None = typer.Option(None, "--out-group", "-og", help="Read-only group (repeatable)"),
    append: bool = typer.Option(False, "--append", "-a", help="Append groups instead of replacing"),
    remove: bool = typer.Option(False, "--remove", "-r", help="Remove specified groups"),
):
    svc = UserMgrService()
    try:
        out = svc.cert_set(
            cert_path=cert_path,
            password=password,
            admin=admin if admin else None,
            fingerprint_override=fingerprint,
            groups=group,
            in_groups=in_group,
            out_groups=out_group,
            append=append,
            remove=remove,
        )
        console.print(Panel.fit(out or "OK", title="cert updated", border_style="green"))
    except UserMgrError as e:
        console.print(Panel.fit(str(e), title="ERROR", border_style="red"))
        raise typer.Exit(1)


@cert_app.command("delete")
def cert_delete(
    ctx: typer.Context,
    cert_path: str = typer.Argument(..., help="Path to certificate (PEM)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    if not yes:
        typer.confirm(f"Delete cert user '{cert_path}'?", abort=True)

    svc = UserMgrService()
    try:
        out = svc.cert_delete(cert_path)
        console.print(Panel.fit(out or "OK", title="cert deleted", border_style="yellow"))
    except UserMgrError as e:
        console.print(Panel.fit(str(e), title="ERROR", border_style="red"))
        raise typer.Exit(1)

