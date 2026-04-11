from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from tak_installer.util import log

SRC_MARTINE_ROOT = None  # resolved from ctx.repo_root
SRC_MARTINE_PKG_ROOT = None
SRC_MARTINE_SERVER_ROOT = None
SRC_MARTINE_BIN_ROOT = None

DST_MARTINE_ROOT = Path("/opt/tak/tools/martine")
DST_MARTINE_PKG_ROOT = DST_MARTINE_ROOT / "martine"
DST_MARTINE_SERVER_ROOT = DST_MARTINE_ROOT / "martine_server"
DST_MARTINE_BIN_ROOT = DST_MARTINE_ROOT / "bin"
DST_MARTINE_STATE_ROOT = DST_MARTINE_ROOT / "state"
DST_MARTINE_VENV = DST_MARTINE_ROOT / ".venv"
DST_MARTINE_MODELS_ROOT = DST_MARTINE_STATE_ROOT / "models"

RSYNC_EXCLUDES = [
    "--exclude=__pycache__/",
    "--exclude=*.pyc",
    "--exclude=*.pyo",
    "--exclude=*.swp",
    "--exclude=*.swo",
    "--exclude=*~",
]

FAST_WHISPER_MODEL_REPO_BY_NAME = {
    "small": "Systran/faster-whisper-small",
    "large-v3": "Systran/faster-whisper-large-v3",
}

FAST_WHISPER_MODEL_DIR_BY_NAME = {
    "small": DST_MARTINE_MODELS_ROOT / "faster-whisper-small",
    "large-v3": DST_MARTINE_MODELS_ROOT / "faster-whisper-large-v3",
}


def _run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if p.returncode != 0:
        raise RuntimeError(f"command failed rc={p.returncode}:\n{' '.join(cmd)}\n\n{p.stdout}")
    if p.stdout.strip():
        log.info(p.stdout.strip())


def _ensure_user_group() -> None:
    if subprocess.run(["getent", "group", "tak"], stdout=subprocess.DEVNULL).returncode != 0:
        _run(["groupadd", "--system", "tak"])

    if subprocess.run(["id", "-u", "tak"], stdout=subprocess.DEVNULL).returncode != 0:
        _run([
            "useradd",
            "--system",
            "--gid", "tak",
            "--home", "/opt/tak",
            "--shell", "/usr/sbin/nologin",
            "tak",
        ])


def _rsync_dir(src: Path, dst: Path) -> None:
    rsync = shutil.which("rsync")
    if not rsync:
        raise RuntimeError("rsync not found")

    dst.mkdir(parents=True, exist_ok=True)

    cmd = [
        rsync,
        "-a",
        "--delete",
        "--no-owner",
        "--no-group",
        *RSYNC_EXCLUDES,
        f"{src}/",
        f"{dst}/",
    ]
    _run(cmd)


def _ensure_runtime_dirs() -> None:
    (DST_MARTINE_STATE_ROOT / "drafts").mkdir(parents=True, exist_ok=True)
    (DST_MARTINE_STATE_ROOT / "cache").mkdir(parents=True, exist_ok=True)
    (DST_MARTINE_STATE_ROOT / "logs").mkdir(parents=True, exist_ok=True)
    DST_MARTINE_MODELS_ROOT.mkdir(parents=True, exist_ok=True)


def _fix_runtime_perms() -> None:
    subprocess.run(["chown", "-R", "tak:tak", str(DST_MARTINE_ROOT)], check=False)
    subprocess.run(["bash", "-lc", f'find "{DST_MARTINE_ROOT}" -path "{DST_MARTINE_VENV}" -prune -o -type d -exec chmod 2770 {{}} \\;'], check=False)
    subprocess.run(["bash", "-lc", f'find "{DST_MARTINE_ROOT}" -path "{DST_MARTINE_VENV}" -prune -o -type f -exec chmod 0660 {{}} \\;'], check=False)
    if DST_MARTINE_BIN_ROOT.exists():
        subprocess.run(["bash", "-lc", f'find "{DST_MARTINE_BIN_ROOT}" -maxdepth 1 -type f -exec chmod 0750 {{}} \\; 2>/dev/null || true'], check=False)


def _read_kv_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}

    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";") or line.startswith("["):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip().lower()] = v.strip()
    return out


def _selected_voice_model_name() -> str:
    conf = _read_kv_file(Path("/opt/tak/tools/takctl/conf.d/martine_voice.conf"))
    return conf.get("model", "small").strip() or "small"


def _ensure_prefetched_models(venv_py: Path) -> None:
    model_name = _selected_voice_model_name()
    repo_id = FAST_WHISPER_MODEL_REPO_BY_NAME.get(model_name)
    local_dir = FAST_WHISPER_MODEL_DIR_BY_NAME.get(model_name)

    if repo_id is None or local_dir is None:
        allowed = ", ".join(sorted(FAST_WHISPER_MODEL_REPO_BY_NAME))
        raise RuntimeError(
            f"unsupported martine voice model '{model_name}', expected one of: {allowed}"
        )

    local_dir.parent.mkdir(parents=True, exist_ok=True)

    log.info(f"martine-runtime: prefetching faster-whisper model {model_name} -> {local_dir}")

    script = r'''
from huggingface_hub import snapshot_download
from pathlib import Path
import sys

repo_id = sys.argv[1]
local_dir = Path(sys.argv[2])

local_dir.parent.mkdir(parents=True, exist_ok=True)
snapshot_download(
    repo_id=repo_id,
    local_dir=str(local_dir),
)
print(f"OK prefetched {repo_id} -> {local_dir}")
'''
    subprocess.run(
        ["sudo", "-u", "tak", str(venv_py), "-c", script, repo_id, str(local_dir)],
        check=True,
    )


def _ensure_venv() -> None:
    venv_py = DST_MARTINE_VENV / "bin" / "python"

    if not venv_py.exists():
        log.info("martine-runtime: creating runtime venv")
        subprocess.run(["python3", "-m", "venv", str(DST_MARTINE_VENV)], check=True)

    subprocess.run(["chown", "-R", "tak:tak", str(DST_MARTINE_VENV)], check=False)

    subprocess.run(
        ["sudo", "-u", "tak", str(venv_py), "-m", "pip", "install", "-q", "--upgrade", "pip", "setuptools", "wheel"],
        check=True,
    )

    subprocess.run(
        [
            "sudo", "-u", "tak", str(venv_py), "-m", "pip", "install", "-q",
            "mcp",
            "requests",
            "boto3",
            "psycopg2-binary",
            "fastembed",
            "pymumble",
            "faster-whisper",
            "ctranslate2",
        ],
        check=True,
    )

    _ensure_prefetched_models(venv_py)


def apply(ctx) -> None:
    log.info("martine-runtime: ensuring user/group")
    _ensure_user_group()

    src_martine_root = Path(ctx.repo_root) / "martine"
    src_martine_pkg_root = src_martine_root / "martine"
    src_martine_server_root = src_martine_root / "martine_server"
    src_martine_bin_root = src_martine_root / "bin"

    if not src_martine_pkg_root.exists():
        raise RuntimeError(f"source tree missing: {src_martine_pkg_root}")

    log.info("martine-runtime: syncing runtime")
    _rsync_dir(src_martine_pkg_root, DST_MARTINE_PKG_ROOT)
    if src_martine_server_root.exists():
        _rsync_dir(src_martine_server_root, DST_MARTINE_SERVER_ROOT)

    if src_martine_bin_root.exists():
        _rsync_dir(src_martine_bin_root, DST_MARTINE_BIN_ROOT)

    _ensure_runtime_dirs()
    _fix_runtime_perms()
    _ensure_venv()

    log.info("martine-runtime: ready")


class _Action:
    ID = "martine-runtime"

    def inspect(self, ctx) -> int:
        print(f"Inspecting {self.ID} action...")
        return 0

    def apply(self, ctx) -> int:
        print(f"Applying {self.ID} action...")
        apply(ctx)
        return 0


ACTION = _Action()
