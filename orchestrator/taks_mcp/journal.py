"""Bounded product journal reads through the existing authenticated node bridge."""
import json
import re


def redact(text):
    text=re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----','[REDACTED KEY]',text,flags=re.S)
    text=re.sub(r'(?im)(authorization\s*[:=]\s*)(?:basic|bearer)\s+\S+',r'\1[REDACTED]',text)
    return re.sub(r'(?im)((?:password|passwd|secret|token|api[_-]?key)[\"\x27]?\s*[=:]\s*)[^\r\n]*',r'\1[REDACTED]',text)


def takctl_journal(api_call, node_id, lines=40):
    if not isinstance(node_id,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',node_id) or type(lines) is not int or not 1<=lines<=100:
        return {'ok':False,'error':'Invalid node ID or line limit'}
    result=api_call('POST','/api/v2/nodes/'+node_id+'/product-journal',{'source':'takctl','lines':lines})
    if not isinstance(result,dict) or result.get('ok') is False:return result
    try:
        payload=json.loads(next(c['text'] for c in result['result']['content'] if c.get('type')=='text'))
        if not isinstance(payload,dict):raise ValueError()
        code=payload['exit_code'];content=redact(str(payload.get('stdout') or ''))[-12000:]
        error=redact(str(payload.get('stderr') or ''))[:1000]
    except (KeyError,ValueError,TypeError,StopIteration):return {'ok':False,'error':'Invalid journal response'}
    common={'source':'takctl','backend':'systemd_journal','unit':'takctl-web.service',
            'coverage':'bounded tail, not a complete activity ledger','inactivity_proof':False}
    if code:return {**common,'ok':False,'error':'Journal read failed','exit_code':code,'detail':error}
    if not content.strip() or content.strip()=='-- No entries --':
        return {**common,'ok':False,'error':'No visible journal entries'}
    return {**common,'ok':True,'content':content}
