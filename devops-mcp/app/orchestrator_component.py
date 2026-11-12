"""Loopback REST bridge for TAKS business operations."""
import json,re,urllib.request,urllib.error
from pathlib import Path
BASE='http://127.0.0.1:8090'
def call(method,path,data=None):
    token=Path('/etc/devops-mcp/service-auth/orchestrator.token').read_text(encoding='ascii').strip()
    if not token:
        return {'ok':False,'error':'Service token unavailable'}
    headers={'Authorization':'Bearer '+token,'Accept':'application/json'}
    if data is not None:headers['Content-Type']='application/json'
    req=urllib.request.Request(BASE+path,data=json.dumps(data).encode() if data is not None else None,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=330 if path.endswith(('/launch','/backup','/verify','/select-restore','/bundles/build','/bundles/readiness')) else 25) as response:return json.loads(response.read(2000000))
    except urllib.error.HTTPError as e:return {'ok':False,'status':e.code,'detail':e.read(2048).decode(errors='replace')}
    except (urllib.error.URLError,TimeoutError) as e:return {'ok':False,'error':str(e)[:300]}
def payload(unit_path,fqdn='',instance_type=''):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*',unit_path):raise ValueError('Invalid unit_path')
    d={'unit_path':unit_path,'role':'tak-node'}
    if fqdn:
        if not re.fullmatch(r'[A-Za-z0-9.-]+',fqdn):raise ValueError('Invalid fqdn')
        d['fqdn']=fqdn
    if instance_type:
        if not re.fullmatch(r'[a-z0-9.]+',instance_type):raise ValueError('Invalid instance_type')
        d['instance_type']=instance_type
    return d
def register_orchestrator_tools(mcp):
    @mcp.tool()
    def taks_units_list()->dict:
        """List organizational units via the orchestrator API."""
        return call('GET','/api/v2/units')
    @mcp.tool()
    def taks_nodes_list()->dict:
        """List TAK nodes with AWS reconciliation and health."""
        return call('GET','/api/v2/nodes')
    @mcp.tool()
    def taks_node_preview(unit_path:str,fqdn:str='',instance_type:str='')->dict:
        """Preview node plan without provisioning; omit sensitive cloud-init data."""
        result=call('POST','/api/v2/nodes/preview',payload(unit_path,fqdn,instance_type))
        return {'plan':result['plan']} if isinstance(result,dict) and 'plan' in result else result
    @mcp.tool()
    def taks_node_dry_run(unit_path:str,fqdn:str='',instance_type:str='')->dict:
        """Run orchestrator AWS dry-run, without provisioning."""
        return call('POST','/api/v2/nodes/dry-run',payload(unit_path,fqdn,instance_type))
    @mcp.tool()
    def taks_node_launch(unit_path:str,confirm_launch:bool=False,fqdn:str='',instance_type:str='')->dict:
        """Launch one paid EC2 node via orchestrator, only after explicit confirmation."""
        if not confirm_launch:return {'ok':False,'confirmation_required':True}
        return launch_checked(unit_path,fqdn,instance_type)


def launch_checked(unit_path, fqdn='', instance_type='', api_call=call):
    request = payload(unit_path, fqdn, instance_type)
    inventory = api_call('GET', '/api/v2/nodes')
    if not isinstance(inventory, dict) or inventory.get('ok') is False or not isinstance(inventory.get('aws', {}).get('instances'), list):
        return {'ok': False, 'error': 'Cannot verify AWS node inventory'}
    for node in inventory['aws']['instances']:
        if (node.get('unit_path') == unit_path or (fqdn and node.get('fqdn') == fqdn)) and node.get('state') not in ('terminated', 'shutting-down'):
            return {'ok': False, 'error': 'AWS node already exists for unit', 'instance_id': node.get('instance_id')}
    return api_call('POST', '/api/v2/nodes/launch', request)
