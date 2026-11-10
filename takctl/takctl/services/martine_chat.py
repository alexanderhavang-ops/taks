"""Shared web/MCP chat transport. Agent execution lives in Martine, not DevOps."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import uuid

POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='martine-chat')
ID = re.compile(r'^[A-Za-z0-9_-]{1,64}$')


def runtime():
    path = '/opt/tak/tools/martine'
    if Path(path).is_dir() and path not in sys.path:
        sys.path.insert(0,path)
    from martine.agent.simple_agent import run_once
    from martine.security import sanitize
    return run_once, sanitize


def database():
    path = Path(os.environ.get('MARTINE_CHAT_DB','/opt/tak/tools/martine/state/chat/chat.sqlite3'))
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA journal_mode=WAL')
    connection.executescript('''CREATE TABLE IF NOT EXISTS jobs
      (id TEXT PRIMARY KEY,owner TEXT,thread TEXT,created REAL,status TEXT,question TEXT,result TEXT);
      CREATE TABLE IF NOT EXISTS actions
      (id TEXT PRIMARY KEY,owner TEXT,created REAL,status TEXT,service TEXT,operation TEXT,arguments TEXT,result TEXT);''')
    path.chmod(0o600)
    return connection


def scope(actor):
    if not actor.get('authenticated'):
        raise PermissionError('Authentication required')
    return '|'.join((actor['unit'],actor['username'],'admin' if actor.get('admin') else 'user'))


def authenticate(username, password):
    from takctl.services.marti_auth import check_selected_user_store
    from takctl.services.business_access import account_actor
    from takctl.web.core.auth_routes import _sign, SESSION_TTL
    if not isinstance(username,str) or not isinstance(password,str) or len(username)>64 or len(password)>1024:
        raise PermissionError('Invalid credentials')
    if not check_selected_user_store(username,password).ok:
        raise PermissionError('Invalid credentials')
    actor=account_actor(username,transport='orchestrator-user')
    return {'ok':True,'ticket':_sign({'u':actor['username'],'exp':time.time()+SESSION_TTL}),
            'user':{'username':actor['username'],'admin':actor['admin']}}


def ticket_actor(ticket):
    from takctl.web.core.auth_routes import _unsign
    from takctl.services.business_access import account_actor
    payload = _unsign(str(ticket))
    if not payload or float(payload.get('exp',0))<time.time():
        raise PermissionError('Session expired')
    return account_actor(str(payload.get('u') or ''),transport='orchestrator-user')


def operator_actor(username):
    from takctl.config import load_config
    return {'username':'orchestrator/'+str(username)[:64], 'unit':str(load_config().get('fqdn') or ''),
            'authenticated':True,'admin':True,'transport':'orchestrator',
            'sender_uid':'','callsign':'','device_uids':(),'channels':()}


def _work(job_id, actor, message, thread):
    try:
        run_once, sanitize = runtime()
        if actor['transport'] != 'orchestrator':
            from takctl.services.business_access import account_actor
            from takctl.services.business_diagnostics import enrich_actor
            current=account_actor(actor['username'],transport=actor['transport'])
            if scope(current) != scope(actor):
                raise PermissionError('Role changed before execution')
            actor = enrich_actor(current)
        with database() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?",(job_id,))
        result=run_once(message,principal=actor,conversation_id=thread)
        public={'ok':bool(result.get('ok')),'answer':sanitize(str(result.get('answer') or '')),
                'run_id':str(result.get('run_id') or ''), 'error': 'Martine could not finish this request' if not result.get('ok') else None}
        with database() as db:
            actions=db.execute("SELECT id,service,operation,arguments FROM actions WHERE owner=? AND status='pending' AND created>?",(scope(actor),time.time()-300)).fetchall()
            public['actions']=[{'id':a['id'],'service':a['service'],'operation':a['operation'],'arguments':sanitize(json.loads(a['arguments']))} for a in actions]
            db.execute("UPDATE jobs SET status='done',result=? WHERE id=?",(json.dumps(public),job_id))
    except Exception:
        with database() as db:
            db.execute("UPDATE jobs SET status='done',result=? WHERE id=?",(json.dumps({'ok':False,'answer':'','error':'Martine is temporarily unavailable. Please retry.'}),job_id))


def submit(actor, message, thread='main'):
    owner=scope(actor)
    if not isinstance(message,str) or not message.strip() or len(message)>8000 or not ID.fullmatch(thread):
        raise ValueError('Message or conversation ID invalid')
    _,sanitize=runtime();message=sanitize(message.strip())
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        recent=db.execute('SELECT count(*) FROM jobs WHERE owner=? AND created>?',(owner,time.time()-60)).fetchone()[0]
        queued=db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running') AND created>?",(time.time()-300,)).fetchone()[0]
        if recent>=6 or queued>=8:
            raise ValueError('Martine is busy; wait a minute before retrying')
        job_id=uuid.uuid4().hex
        db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?)',(job_id,owner,thread,time.time(),'queued',message,None))
    POOL.submit(_work,job_id,dict(actor),message,thread)
    return {'ok':True,'job_id':job_id,'status':'queued'}


def job(actor, job_id):
    if not ID.fullmatch(job_id):
        raise ValueError('Invalid job ID')
    with database() as db:
        row=db.execute('SELECT * FROM jobs WHERE id=? AND owner=?',(job_id,scope(actor))).fetchone()
    if row is None:
        raise PermissionError('Conversation unavailable')
    if row['status']!='done' and row['created']<time.time()-300:
        return {'status':'done','ok':False,'error':'Request interrupted; please retry'}
    return {'job_id':job_id,'status':row['status'],**(json.loads(row['result']) if row['result'] else {})}


def history(actor, thread='main'):
    if not ID.fullmatch(thread):
        raise ValueError('Invalid conversation ID')
    with database() as db:
        rows=db.execute("SELECT question,result FROM jobs WHERE owner=? AND thread=? AND status='done' ORDER BY created DESC LIMIT 30",(scope(actor),thread)).fetchall()
    messages=[]
    for row in reversed(rows):
        messages.append({'role':'user','text':row['question']})
        result=json.loads(row['result'] or '{}')
        messages.append({'role':'assistant','text':result.get('answer') or result.get('error') or ''})
    return {'ok':True,'messages':messages}


def propose_change(actor, service, operation, arguments):
    if not actor.get('admin'):
        raise PermissionError('Administrator required')
    from takctl.services.business_services import WRITES, ARGUMENTS
    if service not in WRITES or operation not in WRITES[service] or not isinstance(arguments,dict):
        raise ValueError('Unsupported business change')
    if set(arguments)-ARGUMENTS.get((service,operation),set()):
        raise ValueError('Unexpected action arguments')
    action_id=uuid.uuid4().hex
    with database() as db:
        db.execute('INSERT INTO actions VALUES(?,?,?,?,?,?,?,?)',(action_id,scope(actor),time.time(),'pending',service,operation,json.dumps(arguments),None))
    return {'confirmation_required':True,'action_id':action_id,'service':service,'operation':operation,
            'message':'Ask the operator to approve this action in the UI. The model cannot approve it.'}


def confirm(actor, action_id):
    if not actor.get('admin') or not ID.fullmatch(action_id):
        raise PermissionError('Administrator required')
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute("SELECT * FROM actions WHERE id=? AND owner=? AND status='pending' AND created>?",(action_id,scope(actor),time.time()-300)).fetchone()
        if row is None:
            raise PermissionError('Action unavailable or expired')
        db.execute("UPDATE actions SET status='executing' WHERE id=?",(action_id,))
    from takctl.services.business_services import call
    _,sanitize=runtime()
    result=sanitize(call(row['service'],row['operation'],json.loads(row['arguments']),write=True,confirm_write=True))
    with database() as db:
        db.execute("UPDATE actions SET status='done',result=? WHERE id=?",(json.dumps(result),action_id))
    return result
