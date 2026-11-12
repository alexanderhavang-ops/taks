"""Bounded lifecycle and backup tools over the existing loopback service bridge."""
from concurrent.futures import ThreadPoolExecutor
import re
import threading
import uuid

from app.orchestrator_component import call, launch_checked, payload

BUCKETS = ('cot_state', 'certs', 'config', 'users', 'documents',
           'takctl_state', 'martine_state', 'replay_state')
NODE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
UNIT = re.compile(r'[A-Za-z0-9_-][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_-][A-Za-z0-9_.-]*)*\Z')
BACKUP = NODE
POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='devops-lifecycle')
LOCK = threading.Lock()
JOBS = {}


def submit(key, work):
    with LOCK:
        for identity, (existing_key, future) in JOBS.items():
            if existing_key == key and not future.done():
                return {'ok': True, 'operation_id': identity, 'status': 'running', 'already_running': True}
        if len(JOBS) >= 32:
            completed = [identity for identity, (_, future) in JOBS.items() if future.done()]
            if not completed:
                return {'ok': False, 'error': 'Operation queue full'}
            del JOBS[completed[0]]
        identity = uuid.uuid4().hex
        JOBS[identity] = (key, POOL.submit(work))
    return {'ok': True, 'operation_id': identity, 'status': 'running'}


def register_lifecycle_tools(mcp, api_call=call):
    @mcp.tool()
    def taks_operation_status(operation_id: str) -> dict:
        """Poll a DevOps operation. Unknown IDs after restart require reconciling inventory/backups before retrying."""
        with LOCK:
            entry = JOBS.get(operation_id)
        if entry is None:
            return {'ok': False, 'status': 'unknown', 'error': 'Operation unavailable; reconcile nodes and backups before retrying'}
        future = entry[1]
        if not future.done():
            return {'ok': True, 'operation_id': operation_id, 'status': 'running'}
        try:
            result = future.result()
        except Exception:
            result = {'ok': False, 'error': 'Operation failed; reconcile before retrying'}
        return {'operation_id': operation_id, 'status': 'done', 'result': result}

    @mcp.tool()
    def taks_backup_buckets() -> dict:
        """List the supported explicit backup bucket names; never read backup contents."""
        return {'ok': True, 'buckets': list(BUCKETS)}

    @mcp.tool()
    def taks_node_backup_start(node_id: str, buckets: list[str], confirm_backup: bool = False) -> dict:
        """Create and store a node state backup asynchronously. Poll taks_operation_status; no backup payload is returned."""
        if not NODE.fullmatch(node_id) or not buckets or len(buckets) > len(BUCKETS) or any(b not in BUCKETS for b in buckets):
            return {'ok': False, 'error': 'Invalid node or backup buckets'}
        if confirm_backup is not True:
            return {'ok': False, 'confirmation_required': True}
        return submit(('backup', node_id), lambda: api_call('POST', '/api/v2/nodes/' + node_id + '/backup', {'buckets': list(dict.fromkeys(buckets))}))

    @mcp.tool()
    def taks_backups_list(unit_path: str) -> dict:
        """List stored backup manifests and restore selection, never archive contents."""
        if not UNIT.fullmatch(unit_path):
            return {'ok': False, 'error': 'Invalid unit path'}
        return api_call('GET', '/api/v2/units/' + unit_path + '/backups')

    @mcp.tool()
    def taks_backup_verify_start(unit_path: str, backup_id: str) -> dict:
        """Verify stored archive paths, unit, format and bucket checksums asynchronously; return only integrity metadata."""
        if not UNIT.fullmatch(unit_path) or not BACKUP.fullmatch(backup_id):
            return {'ok': False, 'error': 'Invalid unit or backup ID'}
        return submit(('verify', unit_path, backup_id), lambda: api_call('POST', '/api/v2/units/' + unit_path + '/backups/' + backup_id + '/verify', {}))

    @mcp.tool()
    def taks_backup_select_restore(unit_path: str, backup_id: str, confirm_select: bool = False) -> dict:
        """Verify and select an existing backup for the next fresh node launch."""
        if not UNIT.fullmatch(unit_path) or not BACKUP.fullmatch(backup_id):
            return {'ok': False, 'error': 'Invalid unit or backup ID'}
        if confirm_select is not True:
            return {'ok': False, 'confirmation_required': True}
        return api_call('POST', '/api/v2/units/' + unit_path + '/backups/' + backup_id + '/select-restore', {})

    @mcp.tool()
    def taks_bundle_prepare_start(unit_path: str, build: bool = False, confirm_build: bool = False) -> dict:
        """Run bundle readiness, or explicitly build a bundle, asynchronously without launching EC2."""
        if not UNIT.fullmatch(unit_path) or type(build) is not bool:
            return {'ok': False, 'error': 'Invalid unit or build flag'}
        if build and confirm_build is not True:
            return {'ok': False, 'confirmation_required': True}
        action = 'build' if build else 'readiness'
        return submit(('bundle', unit_path), lambda: api_call('POST', '/api/v2/bundles/' + action, {'unit_path': unit_path, 'role': 'tak-node'}))

    @mcp.tool()
    def taks_node_launch_start(unit_path: str, fqdn: str = '', instance_type: str = 't3.medium', confirm_launch: bool = False) -> dict:
        """Launch a paid node asynchronously after AWS duplicate checks. Poll operation status and inventory before retrying."""
        if not UNIT.fullmatch(unit_path):
            return {'ok': False, 'error': 'Invalid unit'}
        try:
            payload(unit_path, fqdn, instance_type)
        except ValueError:
            return {'ok': False, 'error': 'Invalid launch arguments'}
        if confirm_launch is not True:
            return {'ok': False, 'confirmation_required': True}
        return submit(('launch', unit_path), lambda: launch_checked(unit_path, fqdn, instance_type, api_call))

    @mcp.tool()
    def taks_node_shutdown(node_id: str, unit_path: str, expected_instance_id: str,
                           backup_id: str, confirm_shutdown: bool = False) -> dict:
        """Terminate the exact registered EC2 node after checking its selected restore backup. Requires explicit confirmation."""
        if not NODE.fullmatch(node_id) or not UNIT.fullmatch(unit_path) or not BACKUP.fullmatch(backup_id) or not re.fullmatch(r'i-[0-9a-f]{8,17}', expected_instance_id):
            return {'ok': False, 'error': 'Invalid identity'}
        if confirm_shutdown is not True:
            return {'ok': False, 'confirmation_required': True}
        inventory = api_call('GET', '/api/v2/nodes')
        if not isinstance(inventory, dict) or inventory.get('ok') is False:
            return {'ok': False, 'error': 'Inventory unavailable'}
        matches = [n for n in inventory.get('items', []) if n.get('node_id') == node_id]
        if len(matches) != 1:
            return {'ok': False, 'error': 'Node not uniquely active'}
        node = matches[0]
        if node.get('unit_path') != unit_path or node.get('aws_instance_id', node.get('instance_id')) != expected_instance_id or node.get('aws_state') not in ('running', 'stopped'):
            return {'ok': False, 'error': 'Node identity or state changed'}
        selection = api_call('GET', '/api/v2/units/' + unit_path + '/backups/restore-selection')
        if selection.get('ok') is not True or selection.get('restore_backup', {}).get('backup_id') != backup_id:
            return {'ok': False, 'error': 'Requested backup is not selected for restore'}
        verified = api_call('POST', '/api/v2/units/' + unit_path + '/backups/' + backup_id + '/verify', {})
        if verified.get('verified') is not True or not set(BUCKETS).issubset(verified.get('buckets', [])):
            return {'ok': False, 'error': 'A verified complete state backup is required'}
        return api_call('POST', '/api/v2/nodes/' + node_id + '/shutdown', {'expected_instance_id': expected_instance_id})
