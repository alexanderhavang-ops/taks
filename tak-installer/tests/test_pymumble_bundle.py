import hashlib
import importlib.util
from pathlib import Path
import sys
import tarfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / 'martine/vendor/pymumble'


class PyMumbleBundleTests(unittest.TestCase):
    def test_wheel_application_code_matches_original_source(self):
        with tarfile.open(VENDOR / 'pymumble-1.6.1.tar.gz') as source, zipfile.ZipFile(VENDOR / 'pymumble-1.6.1-py3-none-any.whl') as wheel:
            modules = [m for m in source.getmembers() if m.isfile() and '/pymumble_py3/' in m.name and m.name.endswith('.py')]
            self.assertGreater(len(modules), 10)
            for member in modules:
                self.assertEqual(source.extractfile(member).read(), wheel.read(member.name.split('/', 1)[1]), member.name)
            self.assertTrue(any(name.endswith('/LICENSE') for name in wheel.namelist()))
            metadata = wheel.read('pymumble-1.6.1.dist-info/METADATA').decode()
            self.assertIn('opuslib==3.0.1', metadata.replace(' ', ''))
            self.assertIn('protobuf==3.12.2', metadata.replace(' ', ''))

    def test_installer_checks_wheel_before_running_package_commands(self):
        sys.path.insert(0, str(ROOT / 'tak-installer'))
        spec = importlib.util.spec_from_file_location('martine_runtime_for_test', ROOT / 'tak-installer/tak_installer/actions/martine_runtime.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        wheel = VENDOR / 'pymumble-1.6.1-py3-none-any.whl'
        self.assertEqual(hashlib.sha256(wheel.read_bytes()).hexdigest(), '2fd030d982ef3a2f84d180fe5f5e544087b0a8f82200e2054057d567426bccbe')
        with patch.object(Path, 'read_bytes', return_value=b'tampered'), patch.object(module.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
                module._ensure_venv(wheel)
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
