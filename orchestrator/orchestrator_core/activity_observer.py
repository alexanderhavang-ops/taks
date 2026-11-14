"""One shared event loop observes CoT and verifies feed completeness against TAK counters."""
import asyncio
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import socket
import ssl
import tarfile
import time
import xml.etree.ElementTree as ET
from .activity import store,instance_id,assessment


class Frames:
    def __init__(self):self.buffer=bytearray()
    def feed(self,data):
        self.buffer.extend(data);result=[]
        while True:
            start=self.buffer.find(b'<event')
            if start<0:
                if len(self.buffer)>65536:raise ValueError('Non-CoT stream')
                break
            end=self.buffer.find(b'</event>',start)
            if end<0:break
            raw=bytes(self.buffer[start:end+8]);del self.buffer[:end+8]
            if len(raw)>65536 or b'<!' in raw:raise ValueError('Invalid CoT frame')
            result.append(ET.fromstring(raw))
        if len(self.buffer)>65536:raise ValueError('Oversized CoT frame')
        return result


def classify(element,bot_uids):
    uid=element.get('uid','');kind=element.get('type','')
    if kind=='t-x-takp-v':return 'control'
    parent=element.find('detail/link')
    origin=parent.get('uid','') if parent is not None and parent.get('relation')=='p-p' else uid
    if uid in bot_uids and kind.startswith('a-'):return 'bot'
    if origin in bot_uids:return 'ambiguous'
    return 'activity'


def prepare(record):
    # Reuse the existing protected unit client identity from a verified selected
    # backup. Nothing is enrolled, no extra map contact is published, no key is returned.
    from .config import load_orch_config
    from .unit_bootstrap import effective_bootstrap_for_bundle
    from .marti_admin import _flatten
    state=Path(load_orch_config().paths.state_dir)
    unit=str(record.get('unit_path') or '')
    host=str(record.get('fqdn') or '')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*',unit) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]+',host) or '..' in host or any(x in ('.','..') for x in unit.split('/')):
        raise ValueError('Invalid registered node')
    bootstrap=effective_bootstrap_for_bundle(unit)
    cfg=_flatten(bootstrap.get('conf_d',{}));secret=_flatten(bootstrap.get('secrets_d',{}))
    root=state/'units'/unit/'backups'
    selected=json.loads((root/'restore-selection.json').read_text())
    backup=selected.get('backup_id') or (selected.get('restore_backup') or {}).get('backup_id')
    if not isinstance(backup,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+',backup):raise ValueError('No selected identity backup')
    folder=root/backup;manifest=json.loads((folder/'manifest.json').read_text())
    expected=manifest['buckets']['certs']['sha256']
    blob=None
    with tarfile.open(folder/'backup.tar.gz','r|gz') as outer:
        for member in outer:
            if member.name.lstrip('./')=='buckets/certs.tar.gz':
                if not member.isfile() or member.size>32*1024*1024:raise ValueError('Invalid certificate archive')
                blob=outer.extractfile(member).read();break
    if blob is None or hashlib.sha256(blob).hexdigest()!=expected:raise ValueError('Identity archive checksum mismatch')
    wanted={'opt/tak/certs/files/martine.pem':'client.pem','opt/tak/certs/files/martine.key':'client.key',
            'opt/tak/certs/files/04_USERS/martine/martine.pem':'client.pem','opt/tak/certs/files/04_USERS/martine/martine.key':'client.key',
            'opt/tak/certs/files/00_CA/ca.pem':'ca.pem','opt/tak/certs/cert-metadata.sh':'metadata',
            'opt/tak/certs/files/'+host+'.pem':'server.pem',
            'opt/tak/certs/files/02_SERVER/takserver-'+host+'.pem':'server.pem'}
    found={}
    with tarfile.open(fileobj=io.BytesIO(blob),mode='r:gz') as inner:
        for member in inner:
            name=member.name.lstrip('./')
            if name in wanted:
                if not member.isfile() or member.size>65536:raise ValueError('Invalid identity member')
                found[wanted[name]]=inner.extractfile(member).read()
    if not {'client.pem','client.key','ca.pem','server.pem'}<=found.keys():raise ValueError('Unit observer identity missing from backup')
    identity=state/'activity/identities'/hashlib.sha256((host+instance_id(record)).encode()).hexdigest()[:24]
    identity.mkdir(parents=True,exist_ok=True,mode=0o700);identity.chmod(0o700)
    for name in ('client.pem','client.key','ca.pem'):
        path=identity/name
        if path.is_symlink():raise ValueError('Identity symlink rejected')
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'wb') as f:f.write(found[name])
        path.chmod(0o600)
    password=secret.get('cert_pass','')
    if not password:
        for line in found.get('metadata',b'').decode().splitlines():
            if line.startswith('PASS='):
                values=shlex.split(line[5:]);password=values[0] if values else ''
    context=ssl.create_default_context(cafile=str(identity/'ca.pem'));context.check_hostname=False
    context.load_cert_chain(str(identity/'client.pem'),str(identity/'client.key'),password=password or None)
    leaf=re.search(rb'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----',found['server.pem'],re.S)
    if not leaf:raise ValueError('Server pin missing')
    pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(leaf[0].decode())).hexdigest()
    return context,pin,host,str(cfg.get('takctl_admin_user') or 'admin'),str(secret.get('takctl_admin_password') or '')


def metrics(host,username,password):
    from .marti_admin import NoRedirect,_access_token,_authorized_open
    import urllib.request
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    token=_access_token(opener,host,username,password)
    result=[]
    for endpoint in ('inputs','subscriptions/all'):
        req=urllib.request.Request('https://'+host+':8446/Marti/api/'+endpoint,headers={'Authorization':'Bearer '+token,'Accept':'application/json'})
        with _authorized_open(opener,req,host,username,password,token) as response:
            raw=response.read(1048577)
            if len(raw)>1048576:raise ValueError('Metrics response too large')
            result.append(json.loads(raw))
    inputs,subscriptions=result
    if not isinstance(inputs.get('data'),list) or not isinstance(subscriptions.get('data'),list):raise ValueError('Incomplete metrics')
    counters={str(r['id']):int(r['messagesReceived']) for r in inputs['data']}
    if not inputs.get('nodeId') or not counters or any(v<0 for v in counters.values()):raise ValueError('Input counters missing')
    bots={str(r['clientUid']) for r in subscriptions['data'] if str(r.get('username','')).lower()=='martine' and str(r.get('ipAddress','')).strip() in ('127.0.0.1','::1') and r.get('clientUid')}
    return (str(inputs.get('nodeId','')),counters),bots


def decode_external_result(result):
    payload=result.get('result') if isinstance(result,dict) else None
    if not isinstance(payload,dict):raise ValueError('Invalid node activity response')
    if 'content' in payload:
        payload=json.loads(next(c['text'] for c in payload['content'] if c.get('type')=='text'))
    # The first version shipped its body directly inside JSON-RPC result.
    if not isinstance(payload,dict) or payload.get('version')!=1 or type(payload.get('complete')) is not bool:
        raise ValueError('Invalid node activity evidence')
    return payload


def external_activity(record):
    import urllib.request
    from .units_state import ensure_unit_orchestrator_secret
    from .marti_admin import NoRedirect
    host=str(record['fqdn']);secret=ensure_unit_orchestrator_secret(record['unit_path'])
    payload={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'service_read','arguments':{'service':'activity','operation':'node_evidence','arguments':{}}}}
    req=urllib.request.Request('https://'+host+'/api/orchestrator/mcp/taks',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+secret,'Content-Type':'application/json'})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    with opener.open(req,timeout=5) as response:
        raw=response.read(16385)
        if len(raw)>16384:raise ValueError('External activity response too large')
    result=json.loads(raw)
    evidence=decode_external_result(result)
    if evidence.get('complete') is not True or not isinstance(evidence.get('epoch'),str):raise ValueError('External activity coverage incomplete')
    return evidence


_OBSERVERS={}
_LOOP=None


async def observe(record):
    node=record['node_id'];instance=instance_id(record);writer=None;failure=None
    state={'instance':instance,'wake':asyncio.Event(),'sampled':asyncio.Event(),'generation':0,'sampling':False}
    _OBSERVERS[node]=state
    ledger=store();ledger.connection(node,instance,False,'Preparing observer identity')
    try:
        context,pin,host,username,password=await asyncio.to_thread(prepare,record)
        reader,writer=await asyncio.wait_for(asyncio.open_connection(host,8089,ssl=context,server_hostname=host,limit=65536),15)
        cert=writer.get_extra_info('ssl_object').getpeercert(binary_form=True)
        if hashlib.sha256(cert).hexdigest()!=pin:raise ValueError('TAK server certificate pin changed')
        sock=writer.get_extra_info('socket');sock.setsockopt(socket.SOL_SOCKET,socket.SO_KEEPALIVE,1)
        if hasattr(socket,'TCP_KEEPIDLE'):sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_KEEPIDLE,30)
        ledger.connection(node,instance,True)
        frames=Frames();count=0;baseline=None;previous_count=0;bots=set();next_sample=0
        pending=asyncio.create_task(reader.read(16384))
        try:
            while True:
                if state['wake'].is_set():state['wake'].clear();next_sample=0
                now=time.monotonic()
                if now>=next_sample:
                    state['sampling']=True
                    sample,bots=await asyncio.to_thread(metrics,host,username,password)
                    try:
                        external=await asyncio.to_thread(external_activity,record)
                        ledger.external(node,instance,external)
                    except Exception:ledger.invalidate_component('node_external:'+node)

                    # Catch data already received while the HTTPS request was in flight.
                    if pending.done():
                        data=pending.result()
                        if not data:raise ConnectionError('TAK stream closed')
                        for element in frames.feed(data):
                            if classify(element,bots)=='control':continue
                            count+=1
                            if baseline is not None:ledger.observed(node,instance,classify(element,bots),element.get('type','')+':'+element.get('uid','')[:100])
                        pending=asyncio.create_task(reader.read(16384))
                    if baseline is not None:
                        same=sample[0]==baseline[0] and sample[1].keys()==baseline[1].keys()
                        deltas=[sample[1][k]-baseline[1][k] for k in baseline[1]] if same else [-1]
                        matched=same and all(d>=0 for d in deltas) and sum(deltas)==count-previous_count
                        ledger.verified(node,instance,matched,'Input delta '+str(sum(deltas))+' versus observed '+str(count-previous_count))
                    baseline=sample;previous_count=count;next_sample=time.monotonic()+30
                    state['sampling']=False;state['generation']+=1;state['sampled'].set()
                wake=asyncio.create_task(state['wake'].wait())
                try:done,_=await asyncio.wait((pending,wake),timeout=max(.01,next_sample-time.monotonic()))
                finally:
                    wake.cancel();await asyncio.gather(wake,return_exceptions=True)
                if pending in done:
                    data=pending.result()
                    if not data:raise ConnectionError('TAK stream closed')
                    for element in frames.feed(data):
                        if classify(element,bots)=='control':continue
                        count+=1;ledger.observed(node,instance,classify(element,bots),element.get('type','')+':'+element.get('uid','')[:100])
                    pending=asyncio.create_task(reader.read(16384))
        finally:
            pending.cancel();await asyncio.gather(pending,return_exceptions=True)
    except asyncio.CancelledError:raise
    except Exception as exc:
        failure='Observer unavailable: '+type(exc).__name__
        ledger.connection(node,instance,False,failure)
        await asyncio.sleep(15)
    finally:
        if _OBSERVERS.get(node) is state:_OBSERVERS.pop(node,None)
        if failure is None:ledger.connection(node,instance,False,'Observer disconnected or restarting')
        if writer:
            writer.close()
            try:await asyncio.wait_for(writer.wait_closed(),2)
            except Exception:pass


async def run():
    global _LOOP
    _LOOP=asyncio.get_running_loop()
    from .nodes_state import list_nodes
    import uuid
    epoch=uuid.uuid4().hex
    tasks={}
    try:
        while True:
            store().component('bridge',epoch)
            records=await asyncio.to_thread(list_nodes)
            wanted={r['node_id']:r for r in records if r.get('node_id') and instance_id(r) and r.get('aws_state')=='running' and r.get('install',{}).get('summary',{}).get('state') in ('succeeded','failed')}
            for node,(instance,task) in list(tasks.items()):
                if node not in wanted or instance_id(wanted[node])!=instance or task.done():
                    task.cancel();await asyncio.gather(task,return_exceptions=True);del tasks[node]
            for node,record in wanted.items():
                if node not in tasks:tasks[node]=(instance_id(record),asyncio.create_task(observe(record)))
            await asyncio.sleep(10)
    finally:
        for _,task in tasks.values():task.cancel()
        await asyncio.gather(*(task for _,task in tasks.values()),return_exceptions=True)


async def refresh(node,instance):
    state=_OBSERVERS.get(node)
    if not state or state['instance']!=instance:return False
    goal=state['generation']+(2 if state['sampling'] else 1)
    state['wake'].set()
    async def wait():
        while state['generation']<goal:
            state['sampled'].clear()
            await state['sampled'].wait()
        return True
    return await asyncio.wait_for(wait(),18)


def fresh_assessment(record):
    if _LOOP is None or not _LOOP.is_running():return {**assessment(record),'eligible_for_idle_shutdown':False,'refresh_completed':False,'reason':'Live activity collector unavailable'}
    future=asyncio.run_coroutine_threadsafe(refresh(record['node_id'],instance_id(record)),_LOOP)
    try:completed=future.result(timeout=20)
    except Exception:
        future.cancel();completed=False
    result=assessment(record)
    if not completed:return {**result,'eligible_for_idle_shutdown':False,'refresh_completed':False,'reason':'Fresh counter and direct-input verification unavailable'}
    return {**result,'refresh_completed':True}
