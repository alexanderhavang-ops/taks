"""One fixed, credential-free deployment operation for the TAKS orchestrator.

Only the public TAKS repository, a pinned commit, and known application directories
are accepted. Persistent state/configuration and the DevOps MCP itself are untouched.
"""

import fcntl
import json
import os
import re
import socket
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

RUNTIME = Path("/opt/tak-orch/orchestrator")
PYTHON = Path("/opt/tak-orch/.venv/bin/python")
SERVICE = "taks-orch.service"
BUSINESS_MCP_SERVICE = "taks-business-mcp.service"
BUSINESS_MCP_HOST = "127.0.0.1"
BUSINESS_MCP_PORT = 8766
HEALTH_URL = "http://127.0.0.1:8090/openapi.json"
GITHUB_ARCHIVE = "https://codeload.github.com/alexanderhavang-ops/taks/tar.gz/"
SHA = re.compile(r"[0-9a-f]{40}\Z")
# Do not touch state/, secrets.d/, conf.d/, bundle, or the existing venv.
CODE_DIRS = (
    "orchestrator_api", "orchestrator_core", "orchestrator_cli",
    "orchestrator_ui", "taks_mcp", "taks_orch", "templates", "bin",
)
ARCHIVE_LIMIT = 80 * 1024 * 1024
FILE_LIMIT = 8 * 1024 * 1024
TOTAL_LIMIT = 160 * 1024 * 1024


class DeployError(Exception):
    pass


def _run(argv, timeout=30, *, env=None, cwd=None):
    try:
        result = subprocess.run(
            argv, stdin=subprocess.DEVNULL, capture_output=True,
            timeout=timeout, env=env, cwd=cwd, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeployError(f"{argv[0]}: {type(exc).__name__}") from exc
    if result.returncode:
        detail = result.stderr[:600].decode("utf-8", "replace").strip()
        raise DeployError(f"{argv[0]} exited {result.returncode}: {detail}")
    return result.stdout[:2000].decode("utf-8", "replace").strip()


def _systemctl(action, service=SERVICE):
    if action not in ("stop", "restart", "is-active") or service not in (SERVICE, BUSINESS_MCP_SERVICE):
        raise ValueError("Unsupported service action")
    if action == "is-active":
        return _run(["/usr/bin/systemctl", action, service], timeout=5)
    return _run(["/usr/bin/sudo", "-n", "/usr/bin/systemctl", action, service], timeout=30)


def _mcp_healthy(attempts=12):
    """Verify Business MCP is active and accepts TCP connections on its loopback port."""
    for trial in range(attempts):
        try:
            if _systemctl("is-active", BUSINESS_MCP_SERVICE) == "active":
                with socket.create_connection((BUSINESS_MCP_HOST, BUSINESS_MCP_PORT), timeout=2):
                    return True
        except (OSError, DeployError):
            pass
        if trial + 1 < attempts:
            time.sleep(1)
    return False

def _healthy(attempts=12):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for trial in range(attempts):
        try:
            with opener.open(HEALTH_URL, timeout=2) as resp:
                if resp.status == 200 and json.loads(resp.read(2_000_000)).get("openapi"):
                    if _systemctl("is-active") == "active":
                        return True
        except (OSError, ValueError, DeployError, urllib.error.URLError):
            pass
        if trial + 1 < attempts:
            time.sleep(1)
    return False


def _fetch_archive(commit_sha, target):
    request = urllib.request.Request(
        GITHUB_ARCHIVE + commit_sha,
        headers={"User-Agent": "taks-devops-mcp/1", "Accept": "application/gzip"},
    )
    total = 0
    with urllib.request.urlopen(request, timeout=40) as response, target.open("wb") as out:
        while True:
            chunk = response.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > ARCHIVE_LIMIT:
                raise DeployError("TAKS archive too large")
            out.write(chunk)
    if not total:
        raise DeployError("Empty TAKS archive")


def _extract_code(archive, target, commit_sha):
    """Copy only regular files in approved directories; reject unsafe archive paths."""
    target.mkdir()
    count = 0
    total = 0
    prefixes = set()
    try:
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar:
                parts = member.name.rstrip("/").split("/")
                if any(p in ("", ".", "..") for p in parts) or member.name.startswith("/"):
                    raise DeployError("Unsafe archive path")
                if not parts[0].startswith("taks-") or not parts[0].endswith(commit_sha):
                    raise DeployError("Unexpected archive revision")
                prefixes.add(parts[0])
                if len(parts) < 3 or parts[1] != "orchestrator" or parts[2] not in CODE_DIRS:
                    continue
                if len(parts) > 16:
                    raise DeployError("Archive path too deep")
                if not (member.isfile() or member.isdir()):
                    raise DeployError("Symlinks and special archive entries forbidden")
                relative = Path(*parts[2:])
                destination = target / relative
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                if member.size > FILE_LIMIT:
                    raise DeployError("Archive member too large")
                count += 1
                total += member.size
                if count > 2000 or total > TOTAL_LIMIT:
                    raise DeployError("Too many archive files")
                destination.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                if source is None:
                    raise DeployError("Missing archive member content")
                with source, destination.open("wb") as dest:
                    shutil.copyfileobj(source, dest)
                destination.chmod(0o755 if member.mode & 0o111 else 0o644)
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise DeployError(f"Invalid archive: {type(exc).__name__}") from exc
    required = (
        "orchestrator_api/app.py", "orchestrator_core/core.py",
        "templates/tak-node.cloud-init.yml.j2",
    )
    if len(prefixes) != 1 or not all((target / p).is_file() for p in required):
        raise DeployError("Archive missing required orchestrator files")
    if not all((target / p).is_dir() for p in CODE_DIRS):
        raise DeployError("Archive missing application directories")
    return count


def _validate_stage(stage):
    for source in stage.rglob("*.py"):
        try:
            compile(source.read_bytes(), str(source), "exec")
        except (SyntaxError, ValueError) as exc:
            raise DeployError(f"Python syntax invalid: {source.name}: {type(exc).__name__}") from exc
    env = os.environ.copy()
    env["PYTHONPATH"] = str(stage)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    _run([str(PYTHON), "-B", "-c", "from orchestrator_api.app import app; assert app"],
         timeout=25, env=env, cwd=str(stage))


def _check_runtime():
    if RUNTIME.is_symlink() or not RUNTIME.is_dir() or not PYTHON.is_file():
        raise DeployError("Expected orchestrator installation unavailable")
    for name in CODE_DIRS:
        path = RUNTIME / name
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise DeployError(f"Unexpected runtime directory: {name}")


def _rollback(moved, backup, discarded):
    errors = []
    for name, had_old in reversed(moved):
        current = RUNTIME / name
        try:
            if current.exists():
                current.rename(discarded / name)
            if had_old:
                (backup / name).rename(current)
        except OSError as exc:
            errors.append(f"{name}: {type(exc).__name__}")
    return errors


def deploy(commit_sha):
    """Stage, validate, swap while stopped, verify; restore previous code on failure."""
    if not isinstance(commit_sha, str) or not SHA.fullmatch(commit_sha):
        return {"ok": False, "error": "A full lowercase 40-character commit SHA is required"}
    try:
        _check_runtime()
        lock = RUNTIME / ".devops-deploy.lock"
        with lock.open("a+") as lock_file:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"ok": False, "error": "Another deployment is in progress"}
            marker = RUNTIME / ".deployed-commit"
            previous = marker.read_text(encoding="ascii").strip() if marker.exists() else "unknown"
            if previous == commit_sha:
                # Reconcile service processes even when code is unchanged (e.g. an
                # earlier deployer updated files but never reloaded Business MCP).
                try:
                    _systemctl("restart", SERVICE)
                    _systemctl("restart", BUSINESS_MCP_SERVICE)
                    if not _healthy() or not _mcp_healthy():
                        raise DeployError("Existing revision failed service health checks")
                except DeployError as exc:
                    return {"ok": False, "commit_sha": commit_sha, "error": str(exc)[:500]}
                return {"ok": True, "already_deployed": True, "commit_sha": commit_sha,
                        "health": "ok", "services": [SERVICE, BUSINESS_MCP_SERVICE]}
            with tempfile.TemporaryDirectory(prefix=".taks-deploy-", dir=RUNTIME, ignore_cleanup_errors=True) as root:
                work = Path(root)
                archive = work / "taks.tar.gz"
                stage = work / "stage"
                backup = work / "backup"
                discarded = work / "discarded"
                backup.mkdir()
                discarded.mkdir()
                _fetch_archive(commit_sha, archive)
                files = _extract_code(archive, stage, commit_sha)
                _validate_stage(stage)
                if not _healthy(attempts=1):
                    raise DeployError("Existing orchestrator is not healthy")
                if not _mcp_healthy(attempts=1):
                    raise DeployError("Existing Business MCP is not healthy")
                moved = []
                stopped = False
                try:
                    _systemctl("stop", BUSINESS_MCP_SERVICE)
                    stopped = True
                    _systemctl("stop", SERVICE)
                    for name in CODE_DIRS:
                        path = RUNTIME / name
                        had_old = path.exists()
                        if had_old:
                            path.rename(backup / name)
                        # Record before the second rename, so partial swaps roll back.
                        moved.append((name, had_old))
                        (stage / name).rename(path)
                    _systemctl("restart", SERVICE)
                    if not _healthy():
                        raise DeployError("New orchestrator did not pass health check")
                    _systemctl("restart", BUSINESS_MCP_SERVICE)
                    if not _mcp_healthy():
                        raise DeployError("New Business MCP did not pass health check")
                    marker.write_text(commit_sha + "\n", encoding="ascii")
                    return {"ok": True, "previous_commit": previous,
                            "commit_sha": commit_sha, "files": files, "health": "ok",
                            "services": [SERVICE, BUSINESS_MCP_SERVICE]}
                except (DeployError, OSError) as exc:
                    problems = _rollback(moved, backup, discarded)
                    restart_error = None
                    if stopped:
                        try:
                            _systemctl("restart", SERVICE)
                            _systemctl("restart", BUSINESS_MCP_SERVICE)
                            if not _healthy() or not _mcp_healthy():
                                restart_error = "Previous orchestrator or Business MCP failed health check"
                        except DeployError as e:
                            restart_error = str(e)
                    return {"ok": False, "error": str(exc)[:500],
                            "commit_sha": commit_sha, "previous_commit": previous,
                            "rollback": "ok" if not problems and not restart_error else "failed",
                            "rollback_errors": problems, "restart_error": restart_error}
    except (DeployError, OSError, ValueError) as exc:
        return {"ok": False, "commit_sha": commit_sha, "error": str(exc)[:500]}


def register_deploy_tool(mcp):
    @mcp.tool()
    def deploy_orchestrator(commit_sha: str, confirm_deploy: bool = False) -> dict:
        """Deploy one pinned public TAKS revision to the orchestrator; verify and roll back on failure."""
        if not confirm_deploy:
            return {"ok": False, "confirmation_required": True}
        return deploy(commit_sha)
