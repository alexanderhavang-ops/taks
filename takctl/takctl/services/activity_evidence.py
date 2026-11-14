"""Node-local, body-free watermarks for direct Martine/XMPP/voice use."""
import hashlib
import json
import os
import shutil
from pathlib import Path
import sqlite3
import threading
import time
import uuid

VERSION=1
ROOT=Path('/opt/tak/tools/takctl/state/activity')
AGENT=Path('/opt/tak/tools/martine/martine/agent/simple_agent.py')
_EPOCH=uuid.uuid4().hex
_LOCK=threading.Lock()
_LAST={}


def _db(root=None):
    managed=root is None
    root=Path(root or ROOT);root.mkdir(parents=True,exist_ok=True,mode=0o750)
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip() if managed else 'test'
    path=root/('direct-inputs-'+boot+'.sqlite')
    db=sqlite3.connect(path,timeout=5)
    path.chmod(0o600)
    if managed and os.geteuid()==0:
        shutil.chown(root,user='tak',group='tak');shutil.chown(path,user='tak',group='tak')
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS components(name TEXT PRIMARY KEY,epoch TEXT,since REAL,last REAL,healthy INTEGER)')
    db.execute('CREATE TABLE IF NOT EXISTS inputs(channel TEXT PRIMARY KEY,last REAL)')
    db.commit();return db


def pulse(component,healthy,*,force=False,root=None,now=None,epoch=None):
    if component not in {'xmpp','voice'}:raise ValueError('Unknown component')
    now=time.time() if now is None else now;epoch=epoch or _EPOCH
    with _LOCK:
        key=(component,bool(healthy))
        if root is None and not force and 0<=now-_LAST.get(key,0)<20:return
        _LAST[key]=now
    db=_db(root)
    try:
        with db:
            row=db.execute('SELECT epoch,since,last,healthy FROM components WHERE name=?',(component,)).fetchone()
            since=(row[1] if row and row[0]==epoch and row[3] and 0<=now-row[2]<=90 else now) if healthy else None
            db.execute('INSERT OR REPLACE INTO components VALUES(?,?,?,?,?)',(component,epoch,since,now,int(bool(healthy))))
    finally:db.close()


def note(channel,*,root=None,now=None):
    if channel not in {'xmpp','voice','agent'}:raise ValueError('Unknown activity channel')
    now=time.time() if now is None else now
    with _LOCK:
        key=('input',channel)
        if root is None and 0<=now-_LAST.get(key,0)<1:return
        _LAST[key]=now
    db=_db(root)
    try:
        with db:db.execute('INSERT OR REPLACE INTO inputs VALUES(?,?)',(channel,now+2))
    finally:db.close()


def snapshot(*,root=None,agent=None,now=None):
    now=time.time() if now is None else now
    try:
        agent=Path(agent or AGENT)
        if 'IDLE_AUDIT_HOOK_VERSION = 1' not in agent.read_text():raise ValueError('Agent activity hook not installed')
        db=_db(root)
        try:
            with db:
                # A write probe makes a failed/unwritable audit ledger explicit.
                db.execute('CREATE TABLE IF NOT EXISTS probe(value INTEGER)')
                db.execute('DELETE FROM probe');db.execute('INSERT INTO probe VALUES(1)')
                rows={r[0]:r[1:] for r in db.execute('SELECT name,epoch,since,last,healthy FROM components')}
                last=db.execute('SELECT MAX(last) FROM inputs').fetchone()[0]
        finally:db.close()
        reasons=[]
        for name in ('xmpp','voice'):
            row=rows.get(name)
            if not row or not row[3] or row[1] is None or not 0<=now-row[2]<=90:reasons.append(name+' audit disconnected, stale or missing')
        epoch=hashlib.sha256(json.dumps([(k,v[:2]) for k,v in sorted(rows.items())],sort_keys=True).encode()).hexdigest()
        return {'ok':True,'version':VERSION,'complete':not reasons,'epoch':epoch,'last_human_event':last,
                'coverage_since':max((v[1] or now for v in rows.values()),default=now),'reasons':reasons,
                'retains_message_bodies':False}
    except Exception as exc:return {'ok':False,'version':VERSION,'complete':False,'reasons':['Node activity audit unavailable: '+type(exc).__name__]}
