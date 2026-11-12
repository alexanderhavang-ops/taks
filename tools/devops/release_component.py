"""Cattle release tools for the authorized taklabs MVP, without SSH or SSM."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.request

from app.orchestrator_component import call, launch_checked
from app.lifecycle_component import submit, register_lifecycle_tools

UNIT = "taklabs"
NODE = "taklabs.aws.tak-hv-sandbox.se"
SEED_PATH = Path("/opt/tak-orch/state/units/taklabs/files/misc/simulation-state.json")
OVERLAYS = (
    "takctl/takctl/simulation/__init__.py", "takctl/takctl/simulation/model.py",
    "takctl/takctl/simulation/daemon.py", "takctl/takctl/web/mcp_domains/simulation_tools.py",
    "takctl/takctl/web/mcp_domains/map_context.py",
    "tak-installer/tak_installer/actions/simulation_runtime.py",
    "tak-installer/plans/tak-node.d/zz-simulation-runtime",
    "takctl/conf.d/simulation.conf.template", "tools/deploy-simulation-mvp.py",
)


def stage_release(commit):
    if not re.fullmatch(r"[a-f0-9]{40}", commit or ""):
        return {"ok": False, "error": "Full pinned TAKS commit required"}
    root = Path("/opt/tak-orch/orchestrator/simulation-releases")
    root.mkdir(exist_ok=True)
    stage = root / commit
    if not stage.exists():
        with tempfile.TemporaryDirectory(dir=root) as tmp:
            temp = Path(tmp)
            url = "https://codeload.github.com/alexanderhavang-ops/taks/tar.gz/" + commit
            with urllib.request.urlopen(url, timeout=40) as r:
                data = r.read(40*1024*1024+1)
            if len(data) > 40*1024*1024:
                raise ValueError("Source archive too large")
            archive = temp / "source.tar.gz"
            archive.write_bytes(data)
            tree = temp / "tree"
            # Retain previously deployed source changes. Overlay only reviewed
            # MVP files, never replace the working Business MCP implementation.
            shutil.copytree("/opt/taks", tree, ignore=shutil.ignore_patterns(
                ".git", ".venv", "__pycache__", "node_modules", "packages", "*.pyc", "*.tar.gz"))
            hashes = {}
            with tarfile.open(archive) as tar:
                for path in OVERLAYS:
                    member = tar.getmember("taks-" + commit + "/" + path)
                    if not member.isfile() or member.size > 200000:
                        raise ValueError("Invalid MVP source member")
                    data = tar.extractfile(member).read()
                    if path.endswith(".py"):
                        compile(data, path, "exec")
                    dst = tree / path
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes(data)
                    hashes[path] = hashlib.sha256(data).hexdigest()
            domain = tree / "takctl/takctl/web/mcp_domains/taks.py"
            hook = ('\nimport sys as _sim_sys\nfrom takctl.web.mcp_domains.simulation_tools '
                    'import install as _install_simulation\n_install_simulation(_sim_sys.modules[__name__])\n')
            text = domain.read_text()
            if "_install_simulation(_sim_sys.modules[__name__])" not in text:
                domain.write_text(text + hook)
            compile(domain.read_text(), str(domain), "exec")
            (tree / "simulation-source-commit").write_text(commit + "\n")
            (tree / "simulation-release.json").write_text(json.dumps({
                "commit": commit, "baseline": "/opt/taks", "overlays": hashes}, indent=2))
            tree.rename(stage)
    # Unit-scoped activation; other nodes retain their normal installer behavior.
    bootstrap = Path("/opt/tak-orch/state/units/taklabs/bootstrap/config.d")
    if not bootstrap.is_dir():
        raise ValueError("taklabs bootstrap configuration not found")
    (bootstrap / "simulation.conf").write_text("simulation_enabled = true\n")
    config = Path("/opt/tak-orch/orchestrator/conf.d/simulation-release.conf")
    config.write_text("bundles_source_repo_root = " + str(stage) + "\n")
    return {"ok": True, "commit": commit, "source_root": str(stage),
            "unit": UNIT, "overlays": list(OVERLAYS)}


class Catalog:
    def __init__(self): self.tools = {}
    def tool(self):
        def register(f): self.tools[f.__name__] = f; return f
        return register


def lifecycle():
    c = Catalog()
    register_lifecycle_tools(c)
    return c.tools


def verify_built_bundle():
    archive = Path("/opt/tak-orch/state/bundles/rendered/taklabs.tar.gz")
    before = archive.stat()
    expected = ["taks-source/" + p for p in OVERLAYS]
    commit_key,config_key = "taks-source/simulation-source-commit", "install/taks-bootstrap/config.d/simulation.conf"
    seed_key = "misc/simulation-state.json"
    expected += [commit_key,config_key]
    seed_hash = hashlib.sha256(SEED_PATH.read_bytes()).hexdigest() if SEED_PATH.is_file() else None
    if seed_hash: expected.append(seed_key)
    found = {}
    with tarfile.open(archive, "r|gz") as tar:
        for member in tar:
            for suffix in expected:
                if member.name == suffix or member.name.endswith("/"+suffix):
                    if not member.isfile():
                        raise ValueError("MVP bundle member is not a file")
                    found[suffix] = True
                    if suffix == seed_key:
                        if member.size > 1048576: raise ValueError("Exercise seed too large")
                        found[suffix] = hashlib.sha256(tar.extractfile(member).read()).hexdigest()
                    elif suffix.endswith(("simulation-source-commit", "config.d/simulation.conf")):
                        if member.size > 1024: raise ValueError("Invalid MVP configuration size")
                        found[suffix] = tar.extractfile(member).read().decode().strip()
            if len(found) == len(expected): break
    after = archive.stat()
    if before.st_mtime_ns != after.st_mtime_ns or before.st_size != after.st_size:
        raise ValueError("Bundle changed during verification; wait and retry")
    missing = sorted(set(expected)-set(found))
    if missing: return {"ok":False,"missing":missing}
    if "simulation_enabled = true" not in found[config_key]:
        return {"ok":False,"error":"Simulation is not enabled in the bundle"}
    if seed_hash and found[seed_key] != seed_hash:
        return {"ok":False,"error":"Exercise seed does not match selected state"}
    return {"ok":True,"bundle":"taklabs.tar.gz","bytes":after.st_size,
            "source_commit":found[commit_key],"simulation_enabled":True,"checked_files":len(found),"exercise_seed_verified":bool(seed_hash)}


def dispatch_release(command):
    p = command.split() if isinstance(command, str) and len(command) < 400 else []
    if len(p) < 2 or p[0] != "taks-release":
        return {"ok": False, "error": "Invalid release command"}
    try:
        op = p[1]
        tools = lifecycle()
        if op == "stage" and len(p) == 3 and re.fullmatch(r"[a-f0-9]{40}",p[2]):
            return submit(("stage",p[2]),lambda:stage_release(p[2]))
        if op == "poll" and len(p) == 3 and re.fullmatch(r"[a-f0-9]{32}",p[2]):
            return tools["taks_operation_status"](p[2])
        if op == "backup" and p[2:] == [NODE,"confirm"]:
            from app.lifecycle_component import BUCKETS
            return tools["taks_node_backup_start"](NODE,list(BUCKETS),True)
        if op == "backups" and p[2:] == [UNIT]:
            return tools["taks_backups_list"](UNIT)
        if op == "restore" and len(p) == 5 and p[2] == UNIT and p[4] == "confirm":
            return tools["taks_backup_select_restore"](UNIT,p[3],True)
        if op == "bundle" and p[2:] == [UNIT,"confirm"]:
            return tools["taks_bundle_prepare_start"](UNIT,True,True)
        if op == "verify" and p[2:] == [UNIT]:
            return submit(("verify-mvp",UNIT),verify_built_bundle)
        if op == "shutdown" and len(p) == 6 and p[2] == NODE and p[5] == "confirm":
            return tools["taks_node_shutdown"](NODE,UNIT,p[3],p[4],True)
        if op == "launch" and p[2:] == [UNIT,"confirm"]:
            return tools["taks_node_launch_start"](UNIT,NODE,"t3.medium",True)
        return {"ok": False, "error": "Unsupported operation, identity, or missing confirmation"}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__ + ": " + str(exc)[:240]}


def register_release_tools(mcp):
    @mcp.tool()
    def taks_release_stage(commit_sha: str, confirm_stage: bool = False) -> dict:
        """Stage pinned TAKS MVP sources for a fresh taklabs cow; never changes the running node."""
        if not confirm_stage: return {"ok":False,"confirmation_required":True}
        return dispatch_release("taks-release stage " + commit_sha)

    @mcp.tool()
    def taks_release_operation(operation_id: str) -> dict:
        """Poll a release, backup, build, or launch operation."""
        return dispatch_release("taks-release poll " + operation_id)
