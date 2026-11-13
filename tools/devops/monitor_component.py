"""Same bounded Linux sampling contract on the orchestrator and registered nodes."""
import re
from app import host_monitor
from app.orchestrator_component import call


def node_read(node_id,operation,arguments):
    if not isinstance(node_id,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',node_id):
        raise ValueError('Invalid registered node ID')
    if operation not in ('process_sample','memory_read','vmstat_sample'):
        raise ValueError('Unknown monitor operation')
    return call('POST','/api/v2/nodes/'+node_id+'/mcp/devops',{'jsonrpc':'2.0','id':1,'method':'tools/call',
        'params':{'name':operation,'arguments':arguments}})


def register_monitor_tools(mcp):
    @mcp.tool()
    def host_process_sample(seconds:float=1,limit:int=20,sort_by:str='cpu')->dict:
        """Sample current CPU, RSS and swap, including whole-host CPU. No process arguments."""
        return host_monitor.sample_snapshot(seconds,limit,sort_by)
    @mcp.tool()
    def host_memory_read()->dict:
        """Read free-style memory, cache, slab, page tables and swap in KiB."""
        return host_monitor.memory_snapshot()
    @mcp.tool()
    def host_vmstat_sample(seconds:float=1,samples:int=3)->dict:
        """Sample vmstat-style CPU, paging, blocked/runnable processes and pressure."""
        return host_monitor.vmstat_samples(seconds,samples)
    @mcp.tool()
    def node_process_sample(node_id:str,seconds:float=1,limit:int=20,sort_by:str='cpu')->dict:
        """Read a bounded process/CPU sample from a registered node over mTLS."""
        host_monitor._validate(seconds,limit,sort_by)
        return node_read(node_id,'process_sample',{'seconds':seconds,'limit':limit,'sort_by':sort_by})
    @mcp.tool()
    def node_memory_read(node_id:str)->dict:
        """Read a registered node's kernel memory counters over mTLS."""
        return node_read(node_id,'memory_read',{})
    @mcp.tool()
    def node_vmstat_sample(node_id:str,seconds:float=1,samples:int=3)->dict:
        """Read bounded vmstat-style samples from a registered node over mTLS."""
        host_monitor._validate(seconds,1,'cpu')
        if type(samples) is not int or not 1<=samples<=5 or seconds*samples>15: raise ValueError('Invalid sample count')
        return node_read(node_id,'vmstat_sample',{'seconds':seconds,'samples':samples})
