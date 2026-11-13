"""Read-only node diagnostics through the existing authenticated mTLS bridge."""
import json
import re

from app.orchestrator_component import call

NODE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
OPERATIONS = frozenset({'tools/list', 'service_status', 'service_logs',
    'takserver_logs', 'takserver_readiness', 'netstat_listeners', 'java_processes'})
SERVICES = frozenset({'takserver.service', 'takctl-web.service', 'nginx.service',
    'postgresql.service', 'slapd.service', 'mumble-server.service',
    'openfire.service', 'martine-cot.service', 'taks-heartbeat.timer'})
SENSITIVE = re.compile(r'password|passwd|secret|token|authorization|private.?key', re.I)


def redact(value):
    if isinstance(value, dict):
        return {key: '[REDACTED]' if SENSITIVE.search(key) else redact(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, (dict, list)):
            return json.dumps(redact(parsed))
        value = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----',
                       '[REDACTED KEY]', value, flags=re.S)
        value = re.sub(r'(?im)(authorization\s*[:=]\s*)(?:basic|bearer)\s+\S+', r'\1[REDACTED]', value)
        return re.sub(r'(?im)((?:password|passwd|secret|token|api[_-]?key|keystorepass)[\"\x27]?\s*[=:]\s*)[^\r\n]*',
                      r'\1[REDACTED]', value)
    return value


def register_node_diagnostics_tools(mcp, api_call=call):
    @mcp.tool()
    def taks_node_devops_probe(node_id: str, operation: str = 'tools/list',
                               service: str = '', lines: int = 40, file: str = '') -> dict:
        """Read bounded node service/TAK Server logs or readiness over mTLS. No arbitrary paths, commands or mutations."""
        if not NODE.fullmatch(node_id) or operation not in OPERATIONS:
            return {'ok': False, 'error': 'Invalid node or read-only operation'}
        if type(lines) is not int or not 1 <= lines <= 80:
            return {'ok': False, 'error': 'Line limit must be 1..80'}
        args = {}
        if operation in ('service_status', 'service_logs'):
            if service not in SERVICES:
                return {'ok': False, 'error': 'Service is not allowlisted'}
            args['service'] = service
        elif service:
            return {'ok': False, 'error': 'Service is not supported for this operation'}
        if file:
            if operation != 'takserver_logs' or file in ('.', '..') or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', file):
                return {'ok': False, 'error': 'Invalid TAK log basename'}
            args['file'] = file
        if operation in ('service_logs', 'takserver_logs'):
            args['lines'] = lines
        rpc = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list' if operation == 'tools/list' else 'tools/call'}
        if operation != 'tools/list':
            rpc['params'] = {'name': operation, 'arguments': args}
        return redact(api_call('POST', '/api/v2/nodes/' + node_id + '/mcp/devops', rpc))
