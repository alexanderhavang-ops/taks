from __future__ import annotations

from datetime import datetime
import re

from takctl.appctx import AppContext
from takctl.domain.models import Client


_TZ_HH_ONLY = re.compile(r"([+-])(\d{2})$")  # matches ...-05 or ...+02


def _parse_pg_ts(s: str) -> datetime:
    """
    Parse Postgres-ish timestamp strings returned by psql_sudo.

    Examples we see:
      - '2026-01-30 08:12:30.716-05'
      - '2026-01-29 10:15:49.408-05'
      - sometimes with +00 or +01 etc

    Python's datetime.fromisoformat requires timezone as ±HH:MM, not ±HH.
    """
    s = s.strip().replace(" ", "T", 1)  # only first space
    s = _TZ_HH_ONLY.sub(lambda m: f"{m.group(1)}{m.group(2)}:00", s)
    return datetime.fromisoformat(s)


class ClientsError(RuntimeError):
    pass


def _preflight_clients(ctx: AppContext) -> None:
    """
    Fail fast with actionable errors instead of a giant traceback.
    """
    # 1) DB connectivity
    try:
        ctx.db.scalar("SELECT 1")
    except Exception as e:
        raise ClientsError(
            "DB connection failed.\n"
            f"db_mode={ctx.cfg.db_mode} host={ctx.cfg.db_host} port={ctx.cfg.db_port} db={ctx.cfg.db_name} user={ctx.cfg.db_user}\n"
            f"error={e}"
        ) from e

    # 2) Required tables exist
    required = ["client_endpoint_event", "client_endpoint"]
    for t in required:
        try:
            ok = ctx.db.scalar(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema=%s AND table_name=%s",
                ("public", t),
            )
        except Exception as e:
            # information_schema access should generally be allowed; if not, give a hint
            raise ClientsError(
                "DB schema check failed (information_schema not readable?).\n"
                "Hint: grant at least USAGE on schema public and SELECT on required tables.\n"
                f"error={e}"
            ) from e

        if str(ok).strip() != "1":
            raise ClientsError(
                f"Missing required table: public.{t}\n"
                "Expected TAK schema to include it.\n"
                "If your schema differs, adjust takctl/services/clients.py query accordingly."
            )

    # 3) Privilege check: do harmless SELECTs
    for t in required:
        try:
            ctx.db.scalar(f"SELECT 1 FROM public.{t} LIMIT 1")
        except Exception as e:
            # Give the exact fix
            raise ClientsError(
                f"Insufficient DB privileges for table public.{t}.\n"
                "Fix (run as postgres):\n"
                f"  GRANT CONNECT ON DATABASE {ctx.cfg.db_name} TO {ctx.cfg.db_user};\n"
                f"  GRANT USAGE ON SCHEMA public TO {ctx.cfg.db_user};\n"
                f"  GRANT SELECT ON TABLE public.{t} TO {ctx.cfg.db_user};\n"
                f"error={e}"
            ) from e


def list_clients(ctx: AppContext, limit: int = 30) -> list[Client]:
    _preflight_clients(ctx)

    q = """
    SELECT ce.callsign,
           ce.uid,
           max(cee.created_ts) AS last_seen
    FROM client_endpoint_event cee
    JOIN client_endpoint ce ON ce.id = cee.client_endpoint_id
    GROUP BY ce.callsign, ce.uid
    ORDER BY last_seen DESC
    LIMIT %s;
    """
    rows = ctx.db.fetchall(q, (limit,))
    out: list[Client] = []

    for callsign, uid, last_seen in rows:
        if isinstance(last_seen, str):
            try:
                last_seen_dt = _parse_pg_ts(last_seen)
            except Exception:
                last_seen_dt = datetime.fromtimestamp(0)
        else:
            last_seen_dt = last_seen

        out.append(Client(callsign=str(callsign), uid=str(uid), last_seen=last_seen_dt))

    return out

