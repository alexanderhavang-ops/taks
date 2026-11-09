#!/usr/bin/env python3
"""Restore an explicitly selected, verified unit backup during fresh provisioning."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

PREFIXES = {
    'certs': ('opt/tak/certs',),
    'config': ('etc/taks/certs', 'opt/tak/CoreConfig.xml', 'opt/tak/core', 'etc/taks-bootstrap.d/config.d', 'etc/taks-bootstrap.d/secrets.d', 'opt/tak/tools/takctl/conf.d', 'opt/tak/tools/takctl/secrets.d', 'etc/taks/mumble-ice-secret', 'etc/taks/mumble-service-password'),
    'users': ('opt/tak/UserAuthenticationFile.xml', 'etc/taks/ldap.conf', 'etc/taks/ldap-secrets.conf', 'etc/ldap', 'state/ldap.ldif'),
    'documents': ('opt/tak/Documents', 'opt/tak/documents', 'opt/tak/tools/takctl/state/docs', 'opt/tak/tools/takctl/data/library/documents'),
    'takctl_state': ('opt/tak/tools/takctl/state', 'opt/tak/takctl-state'),
    'martine_state': ('opt/tak/tools/martine/runtime/identity', 'opt/tak/tools/martine/state/voice_onboarding', 'opt/tak/tools/martine/state/voice_transcribe'),
    'replay_state': ('opt/tak/replay',),
}


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(chunk)
    return checksum.hexdigest()


def validate_member(member, prefixes):
    name = member.name.rstrip('/')
    parts = PurePosixPath(name).parts
    if not name or name.startswith('/') or '..' in parts or '\\' in name:
        raise ValueError('Unsafe archive path: ' + name)
    if not any(name == p or name.startswith(p + '/') for p in prefixes):
        raise ValueError('Unexpected restore path: ' + name)
    if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
        raise ValueError('Unsupported archive member type: ' + name)
    if member.issym() or member.islnk():
        target = member.linkname
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target) if member.issym() else target)
        if target.startswith('/') or not any(resolved == p or resolved.startswith(p + '/') for p in prefixes):
            raise ValueError('Unsafe archive link: ' + name)


def unpack_paths(data, bucket, destination):
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        members = archive.getmembers()
        for member in members:
            validate_member(member, PREFIXES[bucket])
        # Extract only into a new staging directory; data filter also rejects
        # symlink escapes, devices, absolute links, and special permission bits.
        archive.extractall(destination, members=members, filter='data')


def overlay(source, destination):
    for child in source.iterdir():
        target = destination / child.name
        if child.is_symlink():
            if target.is_symlink() or target.is_file():
                target.unlink()
            elif target.exists():
                raise ValueError('Refusing to replace directory with link: ' + str(target))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(os.readlink(child))
        elif child.is_dir():
            if target.is_symlink():
                target.unlink()
            target.mkdir(parents=True, exist_ok=True)
            overlay(child, target)
            shutil.copystat(child, target)
        else:
            if target.is_symlink():
                target.unlink()
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, target)


def validate_backup(artifact, unit=None):
    with tarfile.open(artifact, 'r:gz') as archive:
        names = archive.getnames()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive entries')
        manifest = json.load(archive.extractfile('manifest.json'))
        if manifest.get('format_version') != 2:
            raise ValueError('Only checksummed format version 2 backups may be restored')
        if unit and manifest.get('node', {}).get('unit') not in (None, '', unit):
            raise ValueError('Backup belongs to a different unit')
        allowed = {'manifest.json'}
        for bucket, spec in manifest['buckets'].items():
            if bucket not in PREFIXES and bucket != 'cot_state':
                raise ValueError('Unsupported restore bucket: ' + bucket)
            filename = 'buckets/' + bucket + ('.pg_dump' if bucket == 'cot_state' else '.tar.gz')
            if spec['bucket_file'] != filename:
                raise ValueError('Unexpected bucket filename')
            allowed.add(filename)
            with tempfile.TemporaryDirectory(prefix='taks-backup-verify-') as tmp:
                path = Path(tmp) / 'bucket'
                with archive.extractfile(filename) as source, path.open('wb') as output:
                    shutil.copyfileobj(source, output)
                if digest(path) != spec['sha256']:
                    raise ValueError('Bucket checksum mismatch: ' + bucket)
                if bucket == 'cot_state':
                    with path.open('rb') as dump:
                        if dump.read(5) != b'PGDMP':
                            raise ValueError('CoT bucket is not a PostgreSQL custom dump')
                else:
                    with tarfile.open(path, 'r:gz') as nested:
                        for member in nested:
                            validate_member(member, PREFIXES[bucket])
        if set(names) != allowed:
            raise ValueError('Unexpected outer archive entries')
        return manifest


def stage_backup(bundle, unit):
    selection = json.loads((bundle / 'restore/selection.json').read_text())
    artifact = bundle / 'restore/backup.tar.gz'
    if selection['unit_path'] != unit or digest(artifact) != selection['sha256']:
        raise ValueError('Restore selection unit or archive checksum mismatch')
    return artifact, selection


def restore(bundle, phase, root=Path('/'), run=subprocess.run):
    selection_path = bundle / 'restore/selection.json'
    if not selection_path.exists():
        print('No restore selected')
        return
    unit_info = json.loads((bundle / 'config/unit.json').read_text())
    unit = unit_info.get('unit_path') or unit_info.get('unit') or unit_info.get('unit_id')
    artifact, selection = stage_backup(bundle, unit)
    validate_backup(artifact, unit)
    if phase == 'early':
        run(['systemctl', 'stop', 'takserver'], check=True)
        if run(['getent', 'group', 'tak'], check=False).returncode:
            run(['groupadd', '--system', 'tak'], check=True)
        if run(['id', '-u', 'tak'], check=False).returncode:
            run(['useradd', '--system', '--gid', 'tak', '--home', '/opt/tak', '--shell', '/usr/sbin/nologin', 'tak'], check=True)
    with tarfile.open(artifact, 'r:gz') as archive:
        manifest = json.load(archive.extractfile('manifest.json'))
        if manifest.get('format_version') != 2 or manifest['backup_id'] != selection['backup_id']:
            raise ValueError('Unsupported or mismatched backup manifest')
        wanted = ['config', 'certs', 'takctl_state', 'martine_state', 'documents', 'replay_state'] if phase == 'early' else ['users', 'cot_state']
        for bucket in wanted:
            spec = manifest['buckets'].get(bucket)
            if not spec:
                continue
            expected_name = 'buckets/' + bucket + ('.pg_dump' if bucket == 'cot_state' else '.tar.gz')
            if spec['bucket_file'] != expected_name:
                raise ValueError('Unexpected bucket filename')
            with tempfile.TemporaryDirectory(prefix='taks-restore-') as tmp:
                temp = Path(tmp)
                path = temp / 'bucket'
                with archive.extractfile(expected_name) as source, path.open('wb') as output:
                    shutil.copyfileobj(source, output)
                if digest(path) != spec['sha256']:
                    raise ValueError('Bucket checksum mismatch: ' + bucket)
                if bucket == 'cot_state':
                    # TAK is stopped; restore ownership and ACLs as postgres.
                    os.chmod(temp, 0o755)
                    os.chmod(path, 0o644)
                    database_name = manifest.get('inventory', {}).get('database', 'cot')
                    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', database_name):
                        raise ValueError('Invalid backup database name')
                    run(['runuser', '-u', 'postgres', '--', 'pg_restore', '--clean', '--if-exists', '--exit-on-error', '-d', database_name, str(path)], check=True)
                else:
                    unpacked = temp / 'paths'
                    unpacked.mkdir()
                    unpack_paths(path.read_bytes(), bucket, unpacked)
                    if bucket == 'users' and (unpacked / 'state/ldap.ldif').exists():
                        run(['systemctl', 'stop', 'slapd'], check=True)
                    for top in ('opt', 'etc'):
                        if (unpacked / top).exists():
                            (root / top).mkdir(parents=True, exist_ok=True)
                            overlay(unpacked / top, root / top)
                    if bucket == 'users':
                        ldif = unpacked / 'state/ldap.ldif'
                        if ldif.exists():
                            database = root / 'var/lib/ldap'
                            database.mkdir(parents=True, exist_ok=True)
                            for old in database.iterdir():
                                if old.name in {'data.mdb', 'lock.mdb'}:
                                    old.unlink()
                            run(['slapadd', '-n', '1', '-l', str(ldif)], check=True)
                            run(['chown', '-R', 'openldap:openldap', str(database), str(root / 'etc/ldap/slapd.d')], check=True)
                            run(['systemctl', 'start', 'slapd'], check=True)
            print('Restored bucket:', bucket)
    if phase == 'early':
        for relative in ('opt/tak/tools/takctl/state', 'opt/tak/takctl-state', 'opt/tak/tools/martine/runtime/identity', 'opt/tak/tools/martine/state'):
            target = root / relative
            if target.exists():
                # tak is created by the TAK package or the first installer action.
                run(['chown', '-R', 'tak:tak', str(target)], check=True)
    report = root / 'var/lib/taks-restore'
    report.mkdir(parents=True, exist_ok=True)
    (report / (phase + '.json')).write_text(json.dumps({'backup_id': selection['backup_id'], 'unit_path': unit, 'phase': phase, 'sha256': selection['sha256'], 'ok': True}))


if __name__ == '__main__':
    if os.geteuid() != 0 or len(sys.argv) != 3 or sys.argv[2] not in {'early', 'databases'}:
        raise SystemExit('Usage (root): restore-state.py BUNDLE_ROOT early|databases')
    restore(Path(sys.argv[1]), sys.argv[2])
