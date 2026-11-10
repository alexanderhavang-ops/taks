from fastapi import APIRouter, HTTPException, Request
from takctl.services import martine_chat as chat
from takctl.services.business_access import request_actor

router = APIRouter(prefix='/api/martine',tags=['martine'])

def actor(request):
    try:
        return request_actor(request)
    except PermissionError:
        raise HTTPException(401,'Authentication required')

def invoke(function,*args):
    try:
        return function(*args)
    except PermissionError:
        raise HTTPException(403,'Not available to this account')
    except ValueError as exc:
        raise HTTPException(400,str(exc))

def csrf(request):
    if request.headers.get('x-taks-chat') != '1':
        raise HTTPException(403,'Chat request header required')

@router.get('/health')
def health(): return {'ok':True,'name':'Martine'}

@router.get('/me')
def me(request:Request):
    a=actor(request)
    return {'authenticated':True,'user':{'username':a['username'],'admin':a['admin']}}

@router.get('/history')
def history(request:Request,conversation_id:str='main'):
    return invoke(chat.history,actor(request),conversation_id)

@router.post('/ask')
async def ask(request:Request):
    csrf(request);a=actor(request);body=await request.json()
    return invoke(chat.submit,a,body.get('message',body.get('question','')),body.get('conversation_id','main'))

@router.get('/jobs/{job_id}')
def job(request:Request,job_id:str):
    return invoke(chat.job,actor(request),job_id)

@router.post('/actions/{action_id}/confirm')
def confirm(request:Request,action_id:str):
    csrf(request)
    return invoke(chat.confirm,actor(request),action_id)

@router.get('/runs/{run_id}/events')
def events(request:Request,run_id:str):
    # Historical unrestricted traces may contain credentials. Never publish them.
    actor(request)
    raise HTTPException(410,'Use scoped conversation history; raw traces are not published')
