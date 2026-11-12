"""Verify stored restore artifacts without returning backup contents."""
import hashlib
from pathlib import Path
import runpy

from .bundles import default_bundle_dir
from .units_state import get_unit_backup


def verify_unit_backup(unit_path, backup_id):
    record = get_unit_backup(unit_path, backup_id)
    artifact = Path(record['artifact_path'])
    validator = runpy.run_path(str(default_bundle_dir() / 'install/restore-state.py'))
    manifest = validator['validate_backup'](artifact, unit_path)
    if manifest.get('backup_id') != backup_id or manifest != record['manifest']:
        raise ValueError('Stored and archived manifests do not match')
    with artifact.open('rb') as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
        checksum = digest.hexdigest()
    return {'ok': True, 'verified': True, 'unit_path': unit_path,
            'backup_id': backup_id, 'sha256': checksum,
            'size_bytes': artifact.stat().st_size,
            'created_at': manifest.get('created_at'),
            'buckets': sorted(manifest['buckets']),
            'inventory': manifest.get('inventory', {})}
