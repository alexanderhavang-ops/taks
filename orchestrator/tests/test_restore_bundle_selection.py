import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from orchestrator_core import bundles

spec = importlib.util.spec_from_file_location('restore_fixtures', Path(__file__).with_name('test_state_restore.py'))
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


class BundleSelectionTests(unittest.TestCase):
    def test_selected_backup_is_verified_and_embedded_for_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = fixtures.StateRestoreTests().setup_bundle(root)
            artifact = source / 'restore/backup.tar.gz'
            with patch.object(bundles, 'get_unit_restore_backup_selection', return_value={'backup_id':'test-backup'}), patch.object(bundles, 'get_unit_backup', return_value={'artifact_path': str(artifact), 'manifest':{'format_version':2}}):
                result = bundles._materialize_restore(root / 'new-cow', 'taklabs')
            embedded = root / 'new-cow/restore/backup.tar.gz'
            self.assertEqual(embedded.read_bytes(), artifact.read_bytes())
            self.assertEqual(embedded.stat().st_mode & 0o777, 0o600)
            self.assertTrue(result['selected'])
            self.assertEqual(json.loads((embedded.parent / 'selection.json').read_text())['unit_path'], 'taklabs')

    def test_no_selection_keeps_fresh_launch_behavior(self):
        with patch.object(bundles, 'get_unit_restore_backup_selection', return_value={}):
            self.assertFalse(bundles._materialize_restore(Path('/unused'), 'taklabs')['selected'])

    def test_legacy_raw_ldap_backups_are_not_silently_restored(self):
        with patch.object(bundles, 'get_unit_restore_backup_selection', return_value={'backup_id':'legacy'}), patch.object(bundles, 'get_unit_backup', return_value={'manifest':{'format_version':1}}):
            with self.assertRaisesRegex(ValueError, 'version 2'):
                bundles._materialize_restore(Path('/unused'), 'taklabs')


if __name__ == '__main__':
    unittest.main()
