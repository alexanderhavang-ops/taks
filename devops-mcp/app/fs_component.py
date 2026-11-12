"""Restricted, standard-library filesystem tools for an existing FastMCP instance."""
import base64
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path

MAX_IO = 256 * 1024
POLICY = os.environ.get("DEVOPS_FS_POLICY", "/etc/devops-mcp/fs-policy.json")

def _path(path, permission):
    if not isinstance(path, str) or not path.startswith("/") or "\x00" in path:
        raise ValueError("Absolute path required")
    if ".." in Path(path).parts:
        raise ValueError("Traversal forbidden")
    target = Path(os.path.normpath(path))
    cursor = Path("/")
    for component in target.parts[1:]:
        cursor = cursor / component
        if cursor.is_symlink():
            raise ValueError("Symlinks forbidden")
    with open(POLICY, encoding="utf-8") as handle:
        roots = json.load(handle)["roots"]
    for root in roots:
        base = os.path.normpath(root["path"])
        if root.get(permission) and (os.path.commonpath((str(target), base)) == base):
            return target
    raise PermissionError("Path not authorized")

def _regular(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Regular file required")
    return info

def register_fs_tools(mcp):
    @mcp.tool()
    def fs_list(path: str, limit: int = 100) -> dict:
        p = _path(path, "read")
        if not p.is_dir():
            raise ValueError("Directory required")
        limit = max(1, min(int(limit), 200))
        entries = []
        with os.scandir(p) as scan:
            for entry in scan:
                if len(entries) >= limit:
                    break
                info = entry.stat(follow_symlinks=False)
                entries.append({"name": entry.name, "size": info.st_size,
                    "type": "symlink" if entry.is_symlink() else
                    "directory" if entry.is_dir(follow_symlinks=False) else
                    "file" if entry.is_file(follow_symlinks=False) else "other"})
        return {"entries": entries}

    @mcp.tool()
    def fs_stat(path: str) -> dict:
        p = _path(path, "read")
        info = p.lstat()
        return {"size": info.st_size, "mode": oct(stat.S_IMODE(info.st_mode)),
                "uid": info.st_uid, "gid": info.st_gid, "mtime": info.st_mtime}

    @mcp.tool()
    def fs_read(path: str, offset: int = 0, length: int = 65536) -> dict:
        p = _path(path, "read")
        _regular(p)
        if not 0 <= offset <= 2**40 or not 1 <= length <= MAX_IO:
            raise ValueError("Invalid range")
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError("Regular file required")
            data = os.pread(fd, length, offset)
        finally:
            os.close(fd)
        return {"base64": base64.b64encode(data).decode("ascii"), "size": len(data), "offset": offset}

    @mcp.tool()
    def fs_hash(path: str) -> dict:
        p = _path(path, "read")
        info = _regular(p)
        if info.st_size > 128 * 1024 * 1024:
            raise ValueError("File too large")
        digest = hashlib.sha256()
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise ValueError("Regular file required")
            for block in iter(lambda: handle.read(65536), b""):
                digest.update(block)
        return {"sha256": digest.hexdigest(), "size": info.st_size}

    @mcp.tool()
    def fs_write(path: str, base64_data: str, sha256: str) -> dict:
        """Create only; never overwrite existing files."""
        p = _path(path, "write")
        if not p.parent.is_dir():
            raise ValueError("Parent directory missing")
        if len(base64_data) > 4 * ((MAX_IO + 2) // 3):
            raise ValueError("Payload too large")
        data = base64.b64decode(base64_data, validate=True)
        if len(data) > MAX_IO:
            raise ValueError("Payload too large")
        digest = hashlib.sha256(data).hexdigest()
        if digest != sha256.lower():
            raise ValueError("SHA-256 mismatch")
        fd, temp = tempfile.mkstemp(prefix=".devops-", dir=p.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp, 0o600)
            _path(path, "write")
            os.link(temp, p, follow_symlinks=False)
            dirfd = os.open(p.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dirfd)
            finally:
                os.close(dirfd)
            return {"sha256": digest, "size": len(data)}
        finally:
            os.unlink(temp)

    @mcp.tool()
    def fs_replace(path: str, base64_data: str, sha256: str,
                   expected_sha256: str) -> dict:
        """Atomically replace an existing regular file only if its SHA-256 matches."""
        p = _path(path, "write")
        if len(base64_data) > 4 * ((MAX_IO + 2) // 3):
            raise ValueError("Payload too large")
        data = base64.b64decode(base64_data, validate=True)
        if len(data) > MAX_IO:
            raise ValueError("Payload too large")
        digest = hashlib.sha256(data).hexdigest()
        if digest != sha256.lower():
            raise ValueError("SHA-256 mismatch")
        if len(expected_sha256) != 64 or any(c not in "0123456789abcdef"
                                            for c in expected_sha256.lower()):
            raise ValueError("Invalid expected SHA-256")
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("Regular file required")
            if info.st_size > 128 * 1024 * 1024:
                raise ValueError("Existing file too large")
            existing = hashlib.sha256()
            with os.fdopen(os.dup(fd), "rb") as handle:
                for block in iter(lambda: handle.read(65536), b""):
                    existing.update(block)
            if existing.hexdigest() != expected_sha256.lower():
                raise ValueError("Existing file SHA-256 mismatch")
            current = p.lstat()
            if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
                raise ValueError("File changed during validation")
            tmpfd, tmp = tempfile.mkstemp(prefix=".devops-replace-", dir=p.parent)
            try:
                with os.fdopen(tmpfd, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fchmod(handle.fileno(), stat.S_IMODE(info.st_mode))
                    os.fchown(handle.fileno(), info.st_uid, info.st_gid)
                    os.fsync(handle.fileno())
                _path(path, "write")
                current = p.lstat()
                if (current.st_dev, current.st_ino, current.st_size,
                    current.st_mtime_ns) != (info.st_dev, info.st_ino,
                                            info.st_size, info.st_mtime_ns):
                    raise ValueError("File changed before replacement")
                os.replace(tmp, p)
                dirfd = os.open(p.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(dirfd)
                finally:
                    os.close(dirfd)
                return {"sha256": digest, "size": len(data),
                        "previous_sha256": expected_sha256.lower()}
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
        finally:
            os.close(fd)

    @mcp.tool()
    def fs_mkdir(path: str) -> dict:
        p = _path(path, "write")
        os.mkdir(p, 0o700)
        return {"created": True}

    @mcp.tool()
    def fs_move(source: str, destination: str) -> dict:
        src = _path(source, "write")
        dst = _path(destination, "write")
        _regular(src)
        if src.parent != dst.parent:
            raise ValueError("Only same-directory moves supported")
        os.link(src, dst, follow_symlinks=False)
        os.unlink(src)
        return {"moved": True}
