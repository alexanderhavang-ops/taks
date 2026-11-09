"""Build the packaging repair from the pinned, bundled upstream source."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'pymumble-1.6.1.tar.gz'
SOURCE_SHA256 = 'c17300413dbf2d754a8b1edf0bb599320bc50bc31b799fc8c91ce1d4ca6774fa'
if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != SOURCE_SHA256:
    raise SystemExit('Upstream source checksum mismatch')
with tempfile.TemporaryDirectory(prefix='taks-pymumble-build-') as tmp:
    with tarfile.open(SOURCE, 'r:gz') as archive:
        archive.extractall(tmp, filter='data')
    source = Path(tmp) / 'pymumble-1.6.1'
    # The sdist omitted this file, although setup.py reads and installs it.
    # Restore it verbatim from the distribution's own dependency metadata.
    (source / 'requirements.txt').write_bytes((source / 'pymumble.egg-info/requires.txt').read_bytes())
    subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-cache-dir', '--no-deps', '--wheel-dir', str(ROOT), str(source)], check=True)
