import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from orchestrator_core import backup_verification as verification
from test_state_restore import StateRestoreTests, tar_bytes


class BackupVerificationTests(unittest.TestCase):
    def test_verifies_actual_archive_without_returning_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = StateRestoreTests().setup_bundle(Path(tmp))
            artifact = root / 'restore/backup.tar.gz'
            with tarfile.open(artifact, 'r:gz') as archive:
                manifest = json.load(archive.extractfile('manifest.json'))
            record = {'artifact_path': str(artifact), 'manifest': manifest}
            with patch.object(verification, 'get_unit_backup', return_value=record):
                result = verification.verify_unit_backup('taklabs', 'test-backup')
                self.assertTrue(result['verified'])
                self.assertEqual(len(result['sha256']), 64)
                self.assertNotIn('preserved-keystore-password', json.dumps(result))
                record['manifest'] = manifest | {'backup_id': 'other'}
                with self.assertRaises(ValueError):
                    verification.verify_unit_backup('taklabs', 'test-backup')

    def test_corrupt_bucket_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = StateRestoreTests().setup_bundle(Path(tmp))
            artifact = root / 'restore/backup.tar.gz'
            with tarfile.open(artifact, 'r:gz') as archive:
                files = {m.name: archive.extractfile(m).read() for m in archive}
            manifest = json.loads(files['manifest.json'])
            files['buckets/cot_state.pg_dump'] = b'PGDMP-corrupt'
            artifact.write_bytes(tar_bytes(files))
            with patch.object(verification, 'get_unit_backup', return_value={'artifact_path': str(artifact), 'manifest': manifest}), self.assertRaises(ValueError):
                verification.verify_unit_backup('taklabs', 'test-backup')
