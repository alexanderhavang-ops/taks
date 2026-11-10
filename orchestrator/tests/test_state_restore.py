import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'orchestrator_core/default_bundle/install/restore-state.py'
spec = importlib.util.spec_from_file_location('state_restore', SCRIPT)
restore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore)


def tar_bytes(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as tf:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


class StateRestoreTests(unittest.TestCase):
    def setup_bundle(self, base):
        bundle = base / 'bundle'
        (bundle / 'config').mkdir(parents=True)
        (bundle / 'restore').mkdir()
        (bundle / 'config/unit.json').write_text(json.dumps({'unit_id': 'taklabs'}))
        payloads = {
            'config': tar_bytes({'etc/taks/certs/PASS': b'preserved-keystore-password'}),
            'certs': tar_bytes({'opt/tak/certs/files/alexander.p12': b'unchanged-client-p12'}),
            'takctl_state': tar_bytes({'opt/tak/takctl-state/onboarding/identities/alexander.json': b'{"callsign":"alexander"}'}),
            'users': tar_bytes({'state/ldap.ldif': b'dn: uid=alexander,dc=taks,dc=local\nuid: alexander\nuserPassword: {SSHA}preserved\n', 'etc/ldap/slapd.d/cn=config.ldif': b'ldap-config'}),
            'cot_state': b'PGDMP-test-fixture',
        }
        manifest = {'format_version': 2, 'backup_id': 'test-backup', 'inventory': {'database': 'cot'}, 'buckets': {}}
        files = {}
        for bucket, data in payloads.items():
            filename = 'buckets/' + bucket + ('.pg_dump' if bucket == 'cot_state' else '.tar.gz')
            files[filename] = data
            manifest['buckets'][bucket] = {'bucket_file': filename, 'sha256': hashlib.sha256(data).hexdigest()}
        files['manifest.json'] = json.dumps(manifest).encode()
        artifact = bundle / 'restore/backup.tar.gz'
        artifact.write_bytes(tar_bytes(files))
        selection = {'unit_path': 'taklabs', 'backup_id': 'test-backup', 'sha256': restore.digest(artifact)}
        (bundle / 'restore/selection.json').write_text(json.dumps(selection))
        return bundle

    def test_both_restore_phases_preserve_files_and_order_database_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            bundle = self.setup_bundle(base)
            root = base / 'root'
            root.mkdir()
            calls = []
            def run(command, **kwargs):
                calls.append(command)
                return subprocess.CompletedProcess(command, 0)
            restore.restore(bundle, 'early', root, run)
            restore.restore(bundle, 'databases', root, run)
            self.assertEqual((root / 'etc/taks/certs/PASS').read_bytes(), b'preserved-keystore-password')
            self.assertEqual((root / 'opt/tak/certs/files/alexander.p12').read_bytes(), b'unchanged-client-p12')
            self.assertTrue((root / 'opt/tak/takctl-state/onboarding/identities/alexander.json').is_file())
            self.assertFalse((root / 'state').exists())
            stop = calls.index(['systemctl', 'stop', 'slapd'])
            slapadd = next(i for i, cmd in enumerate(calls) if cmd[0] == 'slapadd')
            start = calls.index(['systemctl', 'start', 'slapd'])
            self.assertLess(stop, slapadd)
            self.assertLess(slapadd, start)
            pg = next(cmd for cmd in calls if 'pg_restore' in cmd)
            self.assertIn('--exit-on-error', pg)
            role = next(cmd for cmd in calls if 'psql' in cmd)
            self.assertLess(calls.index(role), calls.index(pg))
            self.assertIn('"takctl_ro" NOLOGIN NOSUPERUSER', role[-1])
            self.assertEqual(json.loads((root / 'var/lib/taks-restore/databases.json').read_text())['backup_id'], 'test-backup')

    def test_restored_reader_role_is_validated_and_uses_managed_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / 'opt/tak/tools/takctl/conf.d/db.conf'
            config.parent.mkdir(parents=True)
            config.write_text('db_user = custom_reader\n')
            calls = []
            restore.ensure_reader_role(root, lambda command, **kwargs: calls.append(command))
            self.assertIn('"custom_reader" NOLOGIN', calls[0][-1])
            config.write_text('db_user = bad; SQL\n')
            with self.assertRaises(ValueError):
                restore.ensure_reader_role(root, lambda *a, **k: self.fail('No SQL with invalid role'))

    def test_corrupt_archive_and_wrong_unit_fail_before_mutation(self):
        for change in ['checksum', 'unit']:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                bundle = self.setup_bundle(Path(tmp))
                selection = bundle / 'restore/selection.json'
                data = json.loads(selection.read_text())
                data['sha256' if change == 'checksum' else 'unit_path'] = 'incorrect'
                selection.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    restore.restore(bundle, 'early', Path(tmp) / 'root', lambda *a, **k: self.fail('Must not execute commands'))

    def test_path_traversal_unexpected_files_and_link_escape_rejected(self):
        for name in ['../../etc/shadow', '/etc/shadow', 'etc/sudoers']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
                restore.unpack_paths(tar_bytes({name: b'bad'}), 'certs', tmp)
        member = tarfile.TarInfo('opt/tak/certs/link')
        member.type = tarfile.SYMTYPE
        member.linkname = '/etc/shadow'
        with self.assertRaises(ValueError):
            restore.validate_member(member, restore.PREFIXES['certs'])

    def test_embedded_bucket_checksum_is_verified_before_any_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self.setup_bundle(Path(tmp))
            artifact = bundle / 'restore/backup.tar.gz'
            with tarfile.open(artifact, 'r:gz') as archive:
                files = {member.name: archive.extractfile(member).read() for member in archive.getmembers()}
            files['buckets/certs.tar.gz'] = tar_bytes({'opt/tak/certs/forged.pem': b'changed'})
            artifact.write_bytes(tar_bytes(files))
            selection = bundle / 'restore/selection.json'
            data = json.loads(selection.read_text())
            data['sha256'] = restore.digest(artifact)
            selection.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'Bucket checksum mismatch'):
                restore.restore(bundle, 'early', Path(tmp) / 'root', lambda *a, **k: self.fail('No mutation permitted'))

    def test_digest_supports_python_without_hashlib_file_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'archive'
            data = b'archive payload' * 100000
            path.write_bytes(data)
            original = getattr(hashlib, 'file_digest', None)
            if original is not None:
                delattr(hashlib, 'file_digest')
            try:
                self.assertEqual(restore.digest(path), hashlib.sha256(data).hexdigest())
            finally:
                if original is not None:
                    hashlib.file_digest = original

    def test_no_selection_is_a_fresh_cow(self):
        with tempfile.TemporaryDirectory() as tmp:
            restore.restore(Path(tmp), 'early', run=lambda *a, **k: self.fail('No restore commands expected'))


if __name__ == '__main__':
    unittest.main()
