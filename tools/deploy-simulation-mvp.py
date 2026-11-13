#!/usr/bin/env python3
"""Install this pinned MVP on a TAK node; preserve all other runtime services/state.

Invoked as root through the restricted DevOps deployment operation. No keys,
passwords or original user records are returned to the caller.
"""
from __future__ import annotations

import argparse
import compileall
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

BASE = Path("/opt/tak/tools/takctl")
ROOT = Path("/opt/tak/simulation")
FILES = (
    "takctl/takctl/simulation/__init__.py",
    "takctl/takctl/simulation/model.py",
    "takctl/takctl/simulation/daemon.py",
    "takctl/takctl/simulation/orbat.py",
    "takctl/takctl/web/mcp_domains/simulation_tools.py",
    "takctl/takctl/web/mcp_domains/map_context.py",
)
HOOK = '''\n# TAKS explicit simulation and reference retrieval extension.\nimport sys as _sim_sys\nfrom takctl.web.mcp_domains.simulation_tools import install as _install_simulation\n_install_simulation(_sim_sys.modules[__name__])\n'''
UNIT = '''[Unit]
Description=TAKS explicit simulation daemon (one asynchronous process)
After=network-online.target takserver.service
Wants=network-online.target

[Service]
Type=simple
User=tak
Group=tak
WorkingDirectory=/opt/tak/tools/takctl
Environment=PYTHONPATH=/opt/tak/tools/takctl
ExecStart=/opt/tak/tools/takctl/.venv/bin/python -m takctl.simulation.daemon
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/tak/simulation
LimitNOFILE=4096
TasksMax=32
MemoryMax=256M

[Install]
WantedBy=multi-user.target
'''


def run(argv, **kwargs):
    p = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=60, **kwargs)
    if p.returncode:
        raise RuntimeError(f"{Path(argv[0]).name} failed (exit {p.returncode}); inspect node locally")
    return p.stdout


def kv(path):
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith(("#", ";")) and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def selected_identity_capacity(source_root, requested=None, runtime_config=Path("/etc/taks-bootstrap.d/config.d/simulation.conf")):
    # Restore can replace /etc bootstrap fragments with an older cow's values.
    # Select the same immutable bundle that supplied the code and exercise seed.
    bundled = Path(source_root).resolve().parent / "install/taks-bootstrap/config.d/simulation.conf" if source_root else None
    if bundled and bundled.is_file():
        value = kv(bundled).get("simulation_identity_capacity")
        if value is not None:
            capacity = int(value)
            origin = "bundle"
        else:
            raise ValueError("Selected simulation bundle lacks identity capacity")
    else:
        capacity = requested if requested is not None else int(kv(runtime_config).get("simulation_identity_capacity", "8"))
        origin = "argument" if requested is not None else "runtime/default"
    if type(capacity) is not int or not 1 <= capacity <= 1024:
        raise ValueError("Simulation identity capacity must be 1..1024")
    return capacity, origin


def install_identity(index, config, secret, group, writer=None):
    name = f"sim-mvp-{index+1:02d}"
    dst = ROOT / "identity" / name
    dst.mkdir(parents=True, exist_ok=True)
    cert_root = Path("/opt/tak/certs")
    files = cert_root / "files"
    candidates = [files / "04_USERS" / name / f"{name}.pem", files / f"{name}.pem"]
    pem = next((p for p in candidates if p.exists()), None)
    env = dict(os.environ)
    metadata = kv(cert_root / "cert-metadata.sh")
    env.update({"COUNTRY": config.get("cert_country", "SE"),
                "STATE": config.get("cert_state", ""), "CITY": config.get("cert_city", ""),
                "ORGANIZATION": config.get("cert_organization", "TAK"),
                "ORGANIZATIONAL_UNIT": config.get("cert_organizational_unit", ""),
                "CAPASS": secret.get("cert_capass", "") or metadata.get("CAPASS", ""),
                "PASS": secret.get("cert_pass", "") or metadata.get("PASS", "")})
    if pem is None:
        if not all(env[k] for k in ("STATE", "CITY", "ORGANIZATIONAL_UNIT", "CAPASS", "PASS")):
            raise RuntimeError("Missing certificate issuer configuration")
        run([str(cert_root / "makeCert.sh"), "client", name], env=env, cwd=str(cert_root))
        pem = next((p for p in candidates if p.exists()), None)
    if pem is None:
        raise RuntimeError("Issued simulation certificate not found")
    shutil.copy2(pem, dst / "client.pem")
    env["TAKS_SIM_KEY_PASS"] = env["PASS"]
    run(["openssl", "pkey", "-in", str(pem.with_suffix(".key")),
         "-passin", "env:TAKS_SIM_KEY_PASS", "-out", str(dst / "client.key")], env=env)
    if writer is None:
        from takctl.services.backing_user_store import build_backing_user_store
        writer = build_backing_user_store()
    # Dedicated non-admin accounts only. Never change real personnel.
    writer.ensure_user(name, password=secrets.token_urlsafe(24), admin=False,
                       groups=[group], certificate_path=str(pem))
    for p in dst.iterdir():
        shutil.chown(p, user="root", group="tak")
        p.chmod(0o640)
    shutil.chown(dst, user="root", group="tak")
    dst.chmod(0o750)
    return {"username": name, "cert_file": str(dst / "client.pem"), "key_file": str(dst / "client.key")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    parser.add_argument("--source-root")
    parser.add_argument("--identities", type=int)
    args = parser.parse_args()
    args.identities, capacity_source = selected_identity_capacity(args.source_root, args.identities)
    if os.geteuid() != 0 or not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        raise ValueError("Root, pinned commit and 1..1024 identities required")
    sys.path[:0] = [str(BASE), "/opt/tak/tools/martine"]
    ROOT.mkdir(exist_ok=True)
    shutil.chown(ROOT, user="tak", group="tak")
    ROOT.chmod(0o750)
    backup = ROOT / "releases" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + args.commit[:12])
    backup.mkdir(parents=True)
    changed = []
    was_active = subprocess.run(["systemctl", "is-active", "--quiet", "taks-simulation.service"]).returncode == 0
    try:
        with tempfile.TemporaryDirectory() as temp:
            contents = {}
            if args.source_root:
                source = Path(args.source_root).resolve()
                for path in FILES:
                    contents[path] = (source / path).read_bytes()
            else:
                archive = Path(temp) / "source.tar.gz"
                url = "https://codeload.github.com/alexanderhavang-ops/taks/tar.gz/" + args.commit
                with urllib.request.urlopen(url, timeout=30) as response:
                    data = response.read(40*1024*1024+1)
                if len(data) > 40*1024*1024:
                    raise ValueError("Archive too large")
                archive.write_bytes(data)
                with tarfile.open(archive) as tar:
                    for path in FILES:
                        member = tar.getmember("taks-" + args.commit + "/" + path)
                        if not member.isfile() or member.size > 200000:
                            raise ValueError("Invalid source member")
                        contents[path] = tar.extractfile(member).read()
            for path, content in contents.items():
                compile(content, path, "exec")
                dst = BASE / Path(path).relative_to("takctl")
                dst.parent.mkdir(parents=True, exist_ok=True)
                save = backup / dst.relative_to(BASE)
                save.parent.mkdir(parents=True, exist_ok=True)
                if dst.exists():
                    shutil.copy2(dst, save)
                changed.append((dst, save))
                dst.write_bytes(content)
                dst.chmod(0o644)
            domain = BASE / "takctl/web/mcp_domains/taks.py"
            original = domain.read_text()
            if "_install_simulation(_sim_sys.modules[__name__])" not in original:
                save = backup / "taks.py"
                shutil.copy2(domain, save)
                changed.append((domain, save))
                compile(original + HOOK, str(domain), "exec")
                domain.write_text(original + HOOK)
            from takctl.config import load_config, load_secrets
            config, secret = load_config(), load_secrets()
            node = kv(Path("/etc/taks-bootstrap.d/config.d/node.conf"))
            fqdn = node.get("node_fqdn") or node.get("fqdn")
            group = node.get("unit_path") or node.get("node_name") or (fqdn or "taklabs").split(".")[0]
            if not fqdn:
                # Public node name is configuration, never inferred from a client.
                fqdn = config.get("node_fqdn", "") or config.get("fqdn", "")
            if not fqdn:
                raise RuntimeError("Node FQDN unavailable")
            progress = ROOT / "provisioning.json"
            def report(stage, count):
                temp_progress=progress.with_suffix(".tmp")
                temp_progress.write_text(json.dumps({"ok":True,"stage":stage,"completed_identities":count,
                    "identity_capacity":args.identities,"capacity_source":capacity_source,"source_commit":args.commit}))
                shutil.chown(temp_progress,user="root",group="tak"); temp_progress.chmod(0o640)
                os.replace(temp_progress,progress)
            report("issuing_identities",0)
            identities = []
            fingerprints = set()
            from takctl.services.backing_user_store import build_backing_user_store
            writer = build_backing_user_store()
            for i in range(args.identities):
                identity = install_identity(i, config, secret, group,writer)
                pem = Path(identity["cert_file"]).read_text()
                leaf = re.search(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",pem,re.S)
                if leaf is None: raise ValueError("Client certificate missing")
                fingerprint = hashlib.sha256(ssl.PEM_cert_to_DER_cert(leaf.group())).hexdigest()
                if fingerprint in fingerprints: raise ValueError("Duplicate client certificate in pool")
                fingerprints.add(fingerprint); identity["cert_sha256"] = fingerprint
                identities.append(identity)
                if (i+1)%16==0 or i+1==args.identities: report("issuing_identities",i+1)
            report("installing_runtime",len(identities))
            ca = Path("/opt/tak/certs/files/00_CA/ca.pem")
            shutil.copy2(ca, ROOT / "ca.pem")
            context = ssl.create_default_context(cafile=str(ca))
            context.check_hostname = False
            context.load_cert_chain(identities[0]["cert_file"], identities[0]["key_file"])
            with socket.create_connection(("127.0.0.1", 8089), timeout=10) as raw:
                with context.wrap_socket(raw, server_hostname=fqdn) as tls:
                    pin = hashlib.sha256(tls.getpeercert(binary_form=True)).hexdigest()
            conf = {"host": "127.0.0.1", "port": 8089, "server_name": fqdn,
                    "server_sha256": pin, "ca_file": str(ROOT / "ca.pem"),
                    "socket": str(ROOT / "control.sock"), "state_file": str(ROOT / "state.json"),
                    "tick_seconds": 10, "identities": identities, "source_commit": args.commit}
            cfgfile = ROOT / "config.json"
            if cfgfile.exists():
                shutil.copy2(cfgfile, backup / "config.json")
            changed.append((cfgfile, backup / "config.json"))
            cfgfile.write_text(json.dumps(conf, indent=2))
            shutil.chown(cfgfile, user="root", group="tak")
            cfgfile.chmod(0o640)
            # Optional exercise seed is runtime data, never source-code state.
            # Carry the selected exercise through cattle replacement without
            # resetting its UIDs or authoritative coordinates.
            seed = Path(args.source_root).parent / "misc/simulation-state.json" if args.source_root else None
            if seed and seed.is_file():
                from takctl.simulation.model import World
                from takctl.simulation.daemon import atomic_json
                state = World(json.loads(seed.read_text()), capacity=len(identities)).state
                slots = [e["identity_slot"] for u in state["units"].values() if u["active"] or state.get("orbat",{}).get("profile") for e in u["entities"]]
                if len(slots) != len(set(slots)) or any(type(s) is not int or not 0 <= s < len(identities) for s in slots):
                    raise ValueError("Invalid exercise seed identity slots")
                statefile=ROOT / "state.json"
                previous=json.loads(statefile.read_text()) if statefile.exists() else {}
                selected=state.get("orbat",{}).get("instance_id")
                if not statefile.exists() or (selected and selected!=previous.get("orbat",{}).get("instance_id")):
                    saved=backup / "state.json"
                    if statefile.exists():shutil.copy2(statefile,saved)
                    changed.append((statefile,saved))
                    atomic_json(statefile, state)
                    shutil.chown(statefile, user="tak", group="tak")
            unitpath = Path("/etc/systemd/system/taks-simulation.service")
            if unitpath.exists():
                shutil.copy2(unitpath, backup / "taks-simulation.service")
            changed.append((unitpath, backup / "taks-simulation.service"))
            unitpath.write_text(UNIT.replace("MemoryMax=256M","MemoryMax=512M") if args.identities>64 else UNIT)
            unitpath.chmod(0o644)
            python = str(BASE / ".venv/bin/python")
            env = dict(os.environ, PYTHONPATH=str(BASE) + ":/opt/tak/tools/martine")
            run([python, "-c", "from takctl.simulation.daemon import Daemon; from takctl.web.mcp_domains import taks; assert any(t['name']=='simulation_read' for t in taks.TOOLS)"], env=env)
            run(["systemctl", "daemon-reload"])
            run(["systemctl", "enable", "taks-simulation.service"])
            run(["systemctl", "restart", "taks-simulation.service"])
            run(["systemctl", "restart", "takctl-web.service"])
            from takctl.web.mcp_domains.simulation_tools import simulation
            ready = False
            for _ in range(20):
                result = simulation("status", {})
                if result.get("ok"):
                    ready = True
                    break
                time.sleep(.5)
            if not ready:
                raise RuntimeError("Simulation daemon failed its Unix control socket health check")
            (ROOT / "source-commit").write_text(args.commit + "\n")
            report("ready",len(identities))
            print(json.dumps({"ok": True, "commit": args.commit, "identities": len(identities),
                              "backup": str(backup), "group": group, "fqdn": fqdn}))
    except Exception:
        if "report" in locals():
            try:report("failed",len(locals().get("identities",[])))
            except Exception:pass
        subprocess.run(["systemctl", "stop", "taks-simulation.service"], capture_output=True)
        for dst, save in reversed(changed):
            if save.exists():
                shutil.copy2(save, dst)
            else:
                dst.unlink(missing_ok=True)
        run(["systemctl", "restart", "takctl-web.service"])
        run(["systemctl", "daemon-reload"])
        if was_active:
            run(["systemctl", "restart", "taks-simulation.service"])
        raise


if __name__ == "__main__":
    main()
