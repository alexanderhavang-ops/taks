"""Short-lived acoustic enrollment tickets and separate revocable watch credentials.

Ticket and credential values are retained as hashes, alongside parent-card references.
No TAK private key or shared
Mumble service password is delivered to the watch. SQLite transactions make replay
and concurrent redemption fail closed across web workers.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from typing import Callable

DB_PATH = Path('/opt/tak/takctl-state/onboarding/watch-voice/credentials.sqlite')
TICKET_TTL = 180
CREDENTIAL_TTL = 30 * 86400


@contextmanager
def _db(path: Path | None = None):
    path = path or DB_PATH
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # O_EXCL guarantees a newly created credential database never has permissive modes.
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    except FileExistsError:
        pass
    db = sqlite3.connect(path, timeout=5)
    try:
        db.execute('CREATE TABLE IF NOT EXISTS tickets (hash TEXT PRIMARY KEY, parent TEXT NOT NULL, username TEXT NOT NULL, issued INTEGER NOT NULL, expires INTEGER NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS credentials (name TEXT PRIMARY KEY, username TEXT NOT NULL, display TEXT NOT NULL, hash TEXT NOT NULL, id INTEGER UNIQUE NOT NULL, expires INTEGER NOT NULL)')
        db.commit()
        yield db
    finally:
        db.close()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def issue(parent: str, username: str, *, path: Path | None = None, now: int | None = None) -> str:
    now = int(time.time()) if now is None else now
    with _db(path) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM tickets WHERE expires <= ?', (now,))
        if db.execute('SELECT count(*) FROM tickets WHERE username=? AND issued>?', (username, now-60)).fetchone()[0] >= 3:
            raise ValueError('Please wait a minute before playing another setup sound')
        ticket = secrets.token_urlsafe(32)
        db.execute('INSERT INTO tickets VALUES (?,?,?,?,?)', (_hash(ticket), parent, username, now, now+TICKET_TTL))
        db.commit()
        return ticket


def redeem(ticket: str, profile: Callable[[str], dict], *, path: Path | None = None, now: int | None = None) -> dict:
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', ticket):
        raise ValueError('Setup link is invalid or expired')
    now = int(time.time()) if now is None else now
    with _db(path) as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT parent,username,expires FROM tickets WHERE hash=?', (_hash(ticket),)).fetchone()
        if not row or row[2] <= now:
            raise ValueError('Setup link is invalid, expired or already used')
        data = profile(row[0])  # Revalidate card expiry, account existence and selected channels.
        if data.pop('_username') != row[1]:
            raise ValueError('Account changed')
        username = row[1]
        db.execute('DELETE FROM credentials WHERE expires <= ?', (now,))
        if db.execute('SELECT count(*) FROM credentials WHERE username=?', (username,)).fetchone()[0] >= 10:
            raise ValueError('Watch limit reached; revoke an old watch before adding another')
        name = 'TW.' + secrets.token_hex(8)
        password = secrets.token_urlsafe(32)
        # Random IDs keep watch identities separate from existing Vx/service IDs.
        for _ in range(20):
            identity = 2_140_000_000 + secrets.randbelow(7_000_000)
            if not db.execute('SELECT 1 FROM credentials WHERE id=?', (identity,)).fetchone():
                break
        else:
            raise ValueError('Could not allocate watch identity')
        display = str(data.pop('_display', username))[:100] + ' (watch)'
        expires = now + CREDENTIAL_TTL
        db.execute('INSERT INTO credentials VALUES (?,?,?,?,?,?)', (name, username, display, _hash(password), identity, expires))
        db.execute('DELETE FROM tickets WHERE hash=?', (_hash(ticket),))
        db.commit()
        return {**data, 'schema': 1, 'username': name, 'displayName': display, 'password': password, 'credentialExpiresAt': expires}


def authenticate(name: str, password: str, *, path: Path | None = None, now: int | None = None):
    if not re.fullmatch(r'TW\.[0-9a-f]{16}', name) or not isinstance(password, str) or len(password) > 128:
        return None
    now = int(time.time()) if now is None else now
    if not (path or DB_PATH).exists():
        return None
    with _db(path) as db:
        row = db.execute('SELECT hash,id,display,expires FROM credentials WHERE name=?', (name,)).fetchone()
        if row and row[3] > now and hmac.compare_digest(row[0], _hash(password)):
            return row[1], row[2]
    return None


def lookup(*, name: str | None = None, identity: int | None = None, path: Path | None = None):
    if not (path or DB_PATH).exists():
        return None
    with _db(path) as db:
        if name is not None:
            row = db.execute('SELECT id,display FROM credentials WHERE name=? AND expires>?', (name, int(time.time()))).fetchone()
        else:
            row = db.execute('SELECT id,display FROM credentials WHERE id=? AND expires>?', (identity, int(time.time()))).fetchone()
        return tuple(row) if row else None


def revoke(username: str, *, path: Path | None = None) -> int:
    with _db(path) as db:
        db.execute('DELETE FROM tickets WHERE username=?', (username,))
        count = db.execute('DELETE FROM credentials WHERE username=?', (username,)).rowcount
        db.commit()
        return count
