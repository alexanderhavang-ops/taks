from __future__ import annotations

from takctl.appctx import AppContext
from takctl.domain.models import Certificate
from takctl.domain.errors import TakctlAssumptionError
from takctl.infra.time import parse_pg_timestamptz


def _detect_cert_expiry_column(ctx: AppContext) -> str:
    """
    Detect which expiry column exists on public.certificate.
    Different TAK/COT versions use different column names.
    """
    q = """
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema='public' AND table_name='certificate'
    """
    cols = {r[0] for r in ctx.db.fetchall(q)}

    candidates = [
        "expiration_date",
        "effective_date",
        "issuance_date",
        "valid_until",
        "valid_to",
        "expires",
        "expiration",
        "validity_end",
        "validity_end_time",
        "not_after",
    ]
    for c in candidates:
        if c in cols:
            return c

    raise TakctlAssumptionError(
        "Could not find a certificate expiry column on public.certificate. "
        + "Found columns: " + ", ".join(sorted(cols))
    )


def _rows_to_certs(ctx: AppContext, rows: list[tuple]) -> list[Certificate]:
    crl_serials = ctx.openssl.crl_revoked_serials(ctx.cfg.crl_path)

    certs: list[Certificate] = []
    for (cid, cuid, subject_dn, expires_val, revoked_in_db, pem) in rows:
        if isinstance(expires_val, str):
            expires_dt = parse_pg_timestamptz(expires_val)
        else:
            expires_dt = expires_val

        if isinstance(revoked_in_db, str):
            revoked_db = revoked_in_db.lower() in ("t", "true", "1", "yes", "y")
        else:
            revoked_db = bool(revoked_in_db)

        serial_hex = None
        revoked_in_crl = None
        if pem:
            serial_hex, _subj = ctx.openssl.cert_serial_subject(pem)
            if serial_hex:
                revoked_in_crl = serial_hex.upper() in crl_serials

        certs.append(
            Certificate(
                id=int(cid),
                client_uid=str(cuid),
                subject_dn=str(subject_dn),
                expires=expires_dt,
                revoked_in_db=revoked_db,
                serial_hex=serial_hex,
                revoked_in_crl=revoked_in_crl,
            )
        )
    return certs


def list_certs(ctx: AppContext, *, client_uid: str | None = None, limit: int = 200) -> list[Certificate]:
    """
    List certificates.
      - If client_uid is provided: list for that client.
      - Else: list latest certs (by id desc) up to limit.
    """
    expiry_col = _detect_cert_expiry_column(ctx)

    if client_uid:
        q = f"""
        SELECT c.id,
               c.client_uid,
               c.subject_dn,
               c.{expiry_col} as expires,
               (c.revocation_date IS NOT NULL) as revoked_in_db,
               regexp_replace(c.certificate, E\\x27[\\r\\n]+\\x27, , g) as certificate
        FROM public.certificate c
        WHERE c.client_uid = %s
        ORDER BY c.id DESC
        LIMIT %s;
        """
        rows = ctx.db.fetchall(q, (client_uid, limit))
        return _rows_to_certs(ctx, rows)

    q = f"""
    SELECT c.id,
           c.client_uid,
           c.subject_dn,
           c.{expiry_col} as expires,
           (c.revocation_date IS NOT NULL) as revoked_in_db,
           regexp_replace(c.certificate, E\\x27[\\r\\n]+\\x27, , g) as certificate
    FROM public.certificate c
    ORDER BY c.id DESC
    LIMIT %s;
    """
    rows = ctx.db.fetchall(q, (limit,))
    return _rows_to_certs(ctx, rows)

def list_all_certs(ctx: AppContext, limit: int = 200) -> list[Certificate]:
    expiry_col = _detect_cert_expiry_column(ctx)

    q = f"""
    SELECT c.id,
           c.client_uid,
           c.subject_dn,
           c.{expiry_col} as expires,
           (c.revocation_date IS NOT NULL) as revoked_in_db,
           regexp_replace(c.certificate, E'[\\r\\n]+', '', 'g') as certificate
    FROM public.certificate c
    ORDER BY c.id DESC
    LIMIT %s;
    """
    rows = ctx.db.fetchall(q, (limit,))

    crl_serials = ctx.openssl.crl_revoked_serials(ctx.cfg.crl_path)

    certs: list[Certificate] = []
    for (cid, cuid, subject_dn, expires_val, revoked_in_db, pem) in rows:
        expires_dt = expires_val
        revoked_db = bool(revoked_in_db)

        serial_hex = None
        revoked_in_crl = None
        if pem:
            serial_hex, _ = ctx.openssl.cert_serial_subject(pem)
            if serial_hex:
                revoked_in_crl = serial_hex.upper() in crl_serials

        certs.append(
            Certificate(
                id=int(cid),
                client_uid=str(cuid),
                subject_dn=str(subject_dn),
                expires=expires_dt,
                revoked_in_db=revoked_db,
                serial_hex=serial_hex,
                revoked_in_crl=revoked_in_crl,
            )
        )
    return certs


def mark_cert_revoked_in_db(ctx: AppContext, cert_id: int) -> None:
    """
    IMPORTANT: This ONLY updates DB state. CRL update is separate.
    """
    q = "UPDATE public.certificate SET revoked = TRUE WHERE id = %s;"
    ctx.db.fetchall(q, (cert_id,))
    ctx.audit.log("cert.revoke_db", f"id={cert_id}")


# Back-compat shim (older CLI expects this name)
def list_certs_for_client(ctx: "AppContext", client_uid: str, limit: int = 200) -> "list[Certificate]":
    return list_certs(ctx, client_uid=client_uid, limit=limit)
