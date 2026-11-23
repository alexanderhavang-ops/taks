#!/usr/bin/env python3
"""Install opt-in exercise streams backed by MediaMTX and the SimKeeper renderer."""

import hashlib
import ipaddress
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path("/opt/tak/simulation")
MEDIA = Path("/usr/local/lib/taks-simulation-media")
UNIT = Path("/etc/systemd/system/taks-simulation-media.service")
UAS_UNIT = UNIT.with_name("taks-simulation-uas.service")
TAK_PYTHON = Path("/opt/tak/tools/takctl/.venv/bin/python")


MEDIAMTX_AMD64 = (
    "https://github.com/bluenviron/mediamtx/releases/download/v1.21.3/mediamtx_v1.21.3_linux_amd64.tar.gz",
    "0a2ea7eba96023631efa1bea7804823a9145b043b6646a8a05798d4ac24ed635",
)


def install_pinned_media_binary(target):
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "amd64"):
        raise ValueError("This pilot MediaMTX release requires Linux amd64")
    url, expected = MEDIAMTX_AMD64
    digest = hashlib.sha256()
    with tempfile.TemporaryFile() as archive:
        total = 0
        with urllib.request.urlopen(url, timeout=20) as response:
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 40_000_000:
                    raise ValueError("MediaMTX release archive exceeds the expected size")
                digest.update(chunk)
                archive.write(chunk)
        if digest.hexdigest() != expected:
            raise ValueError("MediaMTX release archive checksum mismatch")
        archive.seek(0)
        with tarfile.open(fileobj=archive, mode="r:gz") as package:
            binary = next((member for member in package if member.name in ("mediamtx", "./mediamtx")), None)
            if binary is None or not binary.isfile() or not 0 < binary.size <= 80_000_000:
                raise ValueError("Expected a regular MediaMTX executable in the release")
            with package.extractfile(binary) as source, target.open("wb") as dest:
                shutil.copyfileobj(source, dest)
    target.chmod(0o755)


def manifest(scene, viewers, fqdn):
    networks = [ipaddress.ip_network(value) for value in viewers]
    if not networks or any(net.prefixlen == 0 for net in networks):
        raise ValueError("Select the client networks allowed to view simulation video")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", fqdn):
        raise ValueError("Invalid simulation video hostname")
    cameras = scene["cameras"]
    if not isinstance(cameras, dict) or not 1 <= len(cameras) <= 4:
        raise ValueError("Configure one to four simulation cameras")
    paths = {}
    urls = {}
    for name in cameras:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", name):
            raise ValueError("Invalid simulation camera path")
        path = f"exercise/{name}"
        paths[path] = {
            "source": "publisher",
            "runOnDemand": (
                f"/usr/bin/python3 {MEDIA}/renderer.py {MEDIA}/scene.json "
                f"{ROOT}/state.json {name} rtsp://127.0.0.1:8554/{path}"
            ),
            "runOnDemandStartTimeout": "10s",
            "runOnDemandCloseAfter": "5s",
        }
        urls[name] = f"rtsp://{fqdn}:8554/{path}"
    config = {
        "rtspAddress": ":8554",
        "rtspTransports": ["tcp"],
        "rtmp": False, "hls": False, "webrtc": False, "srt": False, "moq": False,
        "authInternalUsers": [
            {"user": "any", "ips": ["127.0.0.1/32"], "permissions": [
                {"action": "publish", "path": path} for path in paths
            ]},
            {"user": "any", "ips": [str(net) for net in networks], "permissions": [
                {"action": "read", "path": path} for path in paths
            ]},
        ],
        "paths": paths,
    }
    return config, urls


def install(source, scene_path, binary_path):
    scene = json.loads(scene_path.read_text())
    config, urls = manifest(scene, scene["viewer_networks"], scene["video_host"])
    MEDIA.mkdir(mode=0o755, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=MEDIA, prefix=".mediamtx-") as work:
        staged = Path(work) / "mediamtx"
        if binary_path.is_file():
            if binary_path.stat().st_size > 80_000_000:
                raise ValueError("The supplied MediaMTX executable is oversized")
            checksum = scene.get("mediamtx_sha256", "")
            with binary_path.open("rb") as binary:
                digest = hashlib.sha256()
                for chunk in iter(lambda: binary.read(1024 * 1024), b""):
                    digest.update(chunk)
                if digest.hexdigest() != checksum:
                    raise ValueError("MediaMTX checksum mismatch")
                binary.seek(0)
                with staged.open("wb") as dest:
                    shutil.copyfileobj(binary, dest)
            staged.chmod(0o755)
        elif scene.get("mediamtx_release") == "v1.21.3":
            install_pinned_media_binary(staged)
        else:
            raise ValueError("Supply a MediaMTX executable or select the pinned pilot release")
        staged.replace(MEDIA / "mediamtx")
    for original, name in ((source / "tools/simulation-video-demo.py", "renderer.py"),
                           (scene_path, "scene.json")):
        shutil.copyfile(original, MEDIA / name)
        (MEDIA / name).chmod(0o644)
    # JSON is valid YAML and avoids interpolating paths into a YAML string.
    (MEDIA / "mediamtx.yml").write_text(json.dumps(config, indent=2) + "\n")
    (MEDIA / "feeds.json").write_text(json.dumps(urls, indent=2) + "\n")
    UNIT.write_text(f"""[Unit]
Description=TAKS exercise camera streams
After=taks-simulation.service
PartOf=taks-simulation.service

[Service]
User=tak
Group=tak
Environment=PYTHONPATH=/opt/tak/tools/takctl
ExecStart={MEDIA}/mediamtx {MEDIA}/mediamtx.yml
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
CPUQuota=75%
MemoryMax=384M

[Install]
WantedBy=taks-simulation.service
""")
    if "uas" not in scene and UAS_UNIT.is_file():
        subprocess.run(["systemctl", "disable", "--now", UAS_UNIT.name], check=True, timeout=30)
    if "uas" in scene:
        uas = dict(scene["uas"])
        uas["video_url"] = urls[uas.pop("camera")]
        (MEDIA / "uas.json").write_text(json.dumps(uas, indent=2) + "\n")
        subprocess.run([str(TAK_PYTHON), "-m", "pip", "install", "--target", str(MEDIA / "uas-deps"),
                        "pymavlink==2.4.50"], check=True, timeout=120)
        UAS_UNIT.write_text(f"""[Unit]
Description=TAKS simulated aircraft ATAK bridge
After=taks-simulation.service
PartOf=taks-simulation.service

[Service]
User=tak
Group=tak
Environment=PYTHONPATH=/opt/tak/tools/takctl:{MEDIA}/uas-deps
ExecStart={TAK_PYTHON} -m takctl.simulation.uas {MEDIA}/uas.json
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=taks-simulation.service
""")
    subprocess.run(["systemctl", "daemon-reload"], check=True, timeout=20)
    services = [UNIT.name, UAS_UNIT.name] if "uas" in scene else [UNIT.name]
    subprocess.run(["systemctl", "enable", "--now", *services], check=True, timeout=30)
    subprocess.run(["systemctl", "restart", *services], check=True, timeout=30)


if __name__ == "__main__":
    install(*(Path(arg) for arg in sys.argv[1:]))
