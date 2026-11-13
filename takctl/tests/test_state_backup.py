import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from takctl.services import orchestrator_backup as backup


class BackupTests(unittest.TestCase):
    def test_create_archive_includes_inventory_checksums_and_private_permissions(self):
        def run(command, **kwargs):
            self.assertEqual(command[:3], ['sudo', '-n', backup.HELPER])
            if command[3] == 'inventory':
                return subprocess.CompletedProcess(command, 0, stdout=b'{"ldap_users":["alexander"],"postgres_rows":{"cot_router":7}}', stderr=b'')
            kwargs['stdout'].write(b'PGDMP-fixture')
            return subprocess.CompletedProcess(command, 0, stderr=b'')
        with tempfile.TemporaryDirectory() as tmp, patch.object(backup, 'STATE_ROOT', Path(tmp) / 'backups'), patch.object(backup, '_node_identity', return_value={'unit':'taklabs'}), patch.object(backup.subprocess, 'run', side_effect=run):
            result = backup.create_backup(['cot_state'])
            self.assertEqual(result['manifest']['format_version'], 2)
            self.assertEqual(result['manifest']['inventory']['ldap_users'], ['alexander'])
            with tarfile.open(result['artifact_path'], 'r:gz') as archive:
                spec = result['manifest']['buckets']['cot_state']
                data = archive.extractfile(spec['bucket_file']).read()
                self.assertEqual(hashlib.sha256(data).hexdigest(), spec['sha256'])
            self.assertEqual(Path(result['artifact_path']).stat().st_mode & 0o777, 0o600)
            self.assertEqual(Path(result['artifact_path']).parent.stat().st_mode & 0o777, 0o700)

    def test_failure_does_not_leave_a_usable_partial_backup(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(backup, 'STATE_ROOT', Path(tmp) / 'backups'), patch.object(backup, '_node_identity', return_value={'unit':'taklabs'}), patch.object(backup, 'backup_inventory', side_effect=ValueError('helper unavailable')):
            with self.assertRaisesRegex(ValueError, 'helper unavailable'):
                backup.create_backup(['users'])
            self.assertEqual(list(backup.STATE_ROOT.iterdir()), [])

    def test_arbitrary_operations_are_rejected(self):
        for name in ['../../etc/shadow', 'shell_exec']:
            with self.assertRaises(ValueError):
                backup._validate_buckets([name])


if __name__ == '__main__':
    unittest.main()
