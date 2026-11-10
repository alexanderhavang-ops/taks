"""Martine UI relay: business API only; no inference or DevOps dependency here."""
import base64
import hashlib
import hmac
import json
from pathlib import Path
import re
import time
import urllib.request
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from orchestrator_core.config import load_secrets_config
from orchestrator_core.nodes_state import get_node, list_nodes
from orchestrator_core.units_state import ensure_unit_orchestrator_secret
from .operator_auth import _cookie_auth_ok, _basic_auth_ok

router=APIRouter()
COOKIE='taks_martine'
NODE=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')


def _secret():
    return load_secrets_config().auth.session_secret.encode()


def _encode(data):
    raw=base64.urlsafe_b64encode(json.dumps(data,separators=(',',':')).encode()).decode()
    return raw+'.'+hmac.new(_secret(),raw.encode(),hashlib.sha256).hexdigest()


def _decode(value):
    try:
        raw,sig=value.rsplit('.',1)
        if not hmac.compare_digest(sig,hmac.new(_secret(),raw.encode(),hashlib.sha256).hexdigest()):
            return None
        data=json.loads(base64.urlsafe_b64decode(raw))
        return data if data['expires']>time.time() else None
    except (ValueError,KeyError,TypeError):
        return None


def _operator(request):
    return _cookie_auth_ok(request) or _basic_auth_ok(request)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None


def _call(node_id,name,arguments):
    if not NODE.fullmatch(node_id): raise HTTPException(400,'Invalid node')
    node=get_node(node_id)
    fqdn=str((node or {}).get('fqdn') or '')
    if not node or not NODE.fullmatch(fqdn) or '.' not in fqdn:
        raise HTTPException(404,'Node unavailable')
    secret=ensure_unit_orchestrator_secret(str(node.get('unit_path') or ''))
    payload={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':arguments}}
    req=urllib.request.Request('https://'+fqdn+'/api/orchestrator/mcp/taks',
                              data=json.dumps(payload).encode(),
                              headers={'Authorization':'Bearer '+secret,'Content-Type':'application/json'})
    try:
        with urllib.request.build_opener(_NoRedirect()).open(req,timeout=35) as response:
            raw=response.read(262145)
        if len(raw)>262144: raise ValueError('Response too large')
        result=json.loads(raw)
        if result.get('error') or result.get('result',{}).get('isError'):
            raise ValueError('Node rejected request')
        content=result['result']['content'][0]['text']
        data=json.loads(content)
        if data.get('denied'):
            raise HTTPException(403,'Not available to this account')
        return data
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502,'Martine node business service is unavailable')


def _actor(request,node_id=''):
    if _operator(request):
        return node_id, {'operator_user':load_secrets_config().auth.operator_user}
    session=_decode(request.cookies.get(COOKIE,'') or '')
    if not session: raise HTTPException(401,'Sign in to Martine')
    if node_id and node_id != session['node_id']: raise HTTPException(403,'Node outside your session')
    return session['node_id'],{'ticket':session['ticket']}


def _csrf(request):
    if request.headers.get('x-taks-chat')!='1': raise HTTPException(403,'Chat request header required')


@router.get('/api/v2/martine/me')
def me(request:Request):
    if _operator(request):
        nodes=[{'node_id':n['node_id'],'label':n.get('unit_path') or n['node_id']} for n in list_nodes() if n.get('fqdn')]
        return {'authenticated':True,'user':{'username':load_secrets_config().auth.operator_user,'admin':True},'nodes':nodes}
    data=_decode(request.cookies.get(COOKIE,'') or '')
    return {'authenticated':bool(data),'user':data.get('user') if data else None,'node_id':data.get('node_id') if data else ''}


@router.post('/api/v2/martine/login')
async def login(request:Request):
    _csrf(request);body=await request.json()
    node=str(body.get('node_id') or '')
    result=_call(node,'chat_authenticate',{'username':body.get('username',''),'password':body.get('password','')})
    if not result.get('ok') or not result.get('ticket'): raise HTTPException(401,'Invalid credentials')
    response=JSONResponse({'ok':True,'user':result['user'],'node_id':node})
    response.set_cookie(COOKIE,_encode({'node_id':node,'ticket':result['ticket'],'user':result['user'],'expires':time.time()+8*3600}),httponly=True,secure=True,samesite='lax',max_age=8*3600,path='/')
    return response


@router.get('/api/v2/martine/history')
def history(request:Request,node_id:str='',conversation_id:str='main'):
    node,actor=_actor(request,node_id)
    return _call(node,'chat_history',{**actor,'conversation_id':conversation_id})


@router.post('/api/v2/martine/ask')
async def ask(request:Request):
    _csrf(request);body=await request.json();node,actor=_actor(request,str(body.get('node_id') or ''))
    return _call(node,'chat_submit',{**actor,'message':body.get('message',''),'conversation_id':body.get('conversation_id','main')})


@router.get('/api/v2/martine/jobs/{job_id}')
def status(request:Request,job_id:str,node_id:str=''):
    node,actor=_actor(request,node_id)
    return _call(node,'chat_status',{**actor,'job_id':job_id})


@router.post('/api/v2/martine/actions/{action_id}/confirm')
async def confirm(request:Request,action_id:str):
    _csrf(request);body=await request.json();node,actor=_actor(request,str(body.get('node_id') or ''))
    return _call(node,'chat_confirm',{**actor,'action_id':action_id})


@router.get('/martine-widget.js')
def widget():
    return FileResponse(Path(__file__).parent/'static/martine-widget.js',media_type='text/javascript')


@router.get('/martine')
def page():
    return HTMLResponse('<!doctype html><html><meta name="viewport" content="width=device-width,initial-scale=1"><title>Martine · TAKS</title><body style="margin:0;background:#11151b;color:#edf2fa;font:15px system-ui"><div id="martine-chat" style="max-width:900px;margin:auto;padding:24px"></div><script src="/martine-widget.js"></script><script>MartineChat.mount(document.getElementById("martine-chat"),{base:"/api/v2/martine",orchestrator:true});</script></body></html>')
