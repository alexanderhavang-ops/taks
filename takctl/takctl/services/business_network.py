"""Admin-only asynchronous, bounded network diagnostics. Independent of Martine/DevOps."""
from concurrent.futures import ThreadPoolExecutor
import ipaddress
import json
import os
from pathlib import Path
import sqlite3
import socket
import time
import uuid

POOL=ThreadPoolExecutor(max_workers=1,thread_name_prefix='network-diagnostic')
DEFAULT_PORTS=[443,8089,8443,8446,5222,64738]

def database():
    path=Path(os.environ.get('TAKS_NETWORK_DB','/opt/tak/takctl-state/network-diagnostics/jobs.sqlite'))
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=5);db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS captures(id TEXT PRIMARY KEY,owner TEXT,created REAL,status TEXT,result TEXT)')
    path.chmod(0o600);return db

def owner(actor):
    if not actor.get('authenticated') or not actor.get('admin'):raise PermissionError('Administrator required')
    return actor['unit']+'|'+actor['username']

def validate(host_ip,ports,seconds,syn_only):
    if not isinstance(host_ip,str) or '%' in host_ip:raise ValueError('Invalid IP')
    if host_ip:
        ip=ipaddress.ip_address(host_ip)
        if ip.is_loopback or ip.is_multicast or ip.is_unspecified:raise ValueError('Use a client unicast IP')
        host_ip=str(ip)
    if ports is None:ports=DEFAULT_PORTS
    if not isinstance(ports,list) or len(ports)>16 or any(type(p)is not int or not 1<=p<=65535 for p in ports):raise ValueError('Invalid port list')
    if not host_ip and not ports:raise ValueError('An IP or port list is required')
    if type(seconds)is not int or not 1<=seconds<=60 or type(syn_only)is not bool:raise ValueError('Invalid limits')
    return {'host_ip':host_ip,'ports':sorted(set(ports)),'seconds':seconds,'syn_only':syn_only}

def _work(identity,args):
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            client.settimeout(70);client.connect('/run/taks-network-capture.sock')
            client.sendall(json.dumps(args,separators=(',',':')).encode()+b'\n')
            raw=b''
            while len(raw)<=131072:
                chunk=client.recv(min(16384,131073-len(raw)))
                if not chunk:break
                raw+=chunk
        data=json.loads(raw) if len(raw)<=131072 else {'ok':False,'error':'Capture response too large'}
    except Exception:data={'ok':False,'error':'Capture unavailable'}
    with database() as db:db.execute("UPDATE captures SET status='done',result=? WHERE id=?",(json.dumps(data),identity))

def start(actor,host_ip='',ports=None,seconds=60,syn_only=True):
    account=owner(actor);args=validate(host_ip,ports,seconds,syn_only);now=time.time()
    if not Path('/run/taks-network-capture.sock').is_socket():
        return {'ok':False,'setup_required':True,'error':'Packet capture service is not enabled on this node'}
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT 1 FROM captures WHERE status='running' AND created>?",(now-90,)).fetchone():raise ValueError('Another capture is active; retry after it completes')
        db.execute('DELETE FROM captures WHERE created<?',(now-86400,))
        identity=uuid.uuid4().hex;db.execute('INSERT INTO captures VALUES(?,?,?,?,?)',(identity,account,now,'running',None))
    POOL.submit(_work,identity,args)
    return {'ok':True,'capture_id':identity,'status':'running',**args}

def status(actor,capture_id):
    account=owner(actor)
    if not isinstance(capture_id,str) or len(capture_id)!=32 or any(c not in '0123456789abcdef' for c in capture_id):raise ValueError('Invalid capture ID')
    with database() as db:row=db.execute('SELECT * FROM captures WHERE id=? AND owner=?',(capture_id,account)).fetchone()
    if row is None:raise PermissionError('Capture unavailable')
    if row['status']=='running' and row['created']<time.time()-90:return {'status':'done','ok':False,'error':'Capture interrupted; start a new capture'}
    return {'capture_id':capture_id,'status':row['status'],**(json.loads(row['result']) if row['result'] else {})}
