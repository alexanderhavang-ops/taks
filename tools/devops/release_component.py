"""Cattle release tools for the authorized taklabs MVP, without SSH or SSM."""
from pathlib import Path
import hashlib
import json
import math
import re
import shutil
import sys
import subprocess
import os
import tarfile
import tempfile
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET

from app.orchestrator_component import call, launch_checked
from app.lifecycle_component import submit, register_lifecycle_tools

UNIT = "taklabs"
NODE = "taklabs.aws.tak-hv-sandbox.se"
SEED_PATH = Path("/opt/tak-orch/state/units/taklabs/files/misc/simulation-state.json")
OVERLAYS = (
    "takctl/takctl/simulation/__init__.py", "takctl/takctl/simulation/model.py",
    "takctl/takctl/simulation/daemon.py", "takctl/takctl/web/mcp_domains/simulation_tools.py",
    "takctl/takctl/simulation/orbat.py", "takctl/takctl/simulation/perception.py",
    "takctl/takctl/web/mcp_domains/map_context.py",
    "takctl/takctl/web/mcp_domains/devops.py",
    "takctl/takctl/web/mcp_domains/host_monitor.py",
    "takctl/takctl/services/ldap_user_store.py",
    "takctl/takctl/services/orchestrator_backup.py",
    "tak-installer/tak_installer/actions/simulation_runtime.py",
    "tak-installer/plans/tak-node.d/zz-simulation-runtime",
    "takctl/conf.d/simulation.conf.template", "tools/deploy-simulation-mvp.py",
)


def map_upstream_probe():
    """Tiny fixed public queries from the orchestrator; no credentials or user URLs."""
    query = urllib.parse.urlencode({"data": "[out:json][timeout:3];node(1);out;"}).encode()
    targets = [("overpass-main-post", "https://overpass-api.de/api/interpreter", query),
               ("overpass-coffee-post", "https://overpass.private.coffee/api/interpreter", query),
               ("overpass-coffee-get", "https://overpass.private.coffee/api/interpreter?"+query.decode(), None),
               ("osm-api-get", "https://api.openstreetmap.org/api/0.6/node/1", None)]
    rows = []
    for name, url, data in targets:
        req = urllib.request.Request(url, data=data, headers={"User-Agent": "TAKS-MapContext/2.0"})
        try:
            with urllib.request.urlopen(req, timeout=6) as response:
                raw = response.read(4096)
                rows.append({"name": name, "status": response.status, "sample_bytes": len(raw)})
        except urllib.error.HTTPError as exc:
            rows.append({"name": name, "status": exc.code})
        except (OSError, ValueError) as exc:
            rows.append({"name": name, "error": type(exc).__name__, "detail": str(exc)[:180]})
    return {"ok": True, "probe_host": "orchestrator", "results": rows}


def map_bbox_probe():
    result = call("POST", "/api/v2/nodes/"+NODE+"/mcp/taks", {"jsonrpc":"2.0","id":1,
        "method":"tools/call","params":{"name":"simulation_read","arguments":{}}})
    status = json.loads(result["result"]["content"][0]["text"])
    center = status["units"][0]["position"]
    dy = math.degrees(500/6371008.8); dx = dy/math.cos(math.radians(center["lat"]))
    bbox = ",".join(str(v) for v in (center["lon"]-dx,center["lat"]-dy,center["lon"]+dx,center["lat"]+dy))
    request = urllib.request.Request("https://api.openstreetmap.org/api/0.6/map?"+urllib.parse.urlencode({"bbox":bbox}),headers={"User-Agent":"TAKS-MapContext/2.0"})
    with urllib.request.urlopen(request,timeout=10) as response:
        data = response.read(4*1024*1024+1)
        if len(data)>4*1024*1024: return {"ok":False,"error":"Area exceeds 4 MiB"}
        root = ET.fromstring(data)
        return {"ok":True,"probe_host":"orchestrator","http_status":response.status,"bytes":len(data),
                "nodes":len(root.findall("node")),"ways":len(root.findall("way"))}


def prepare_staging_roster(commit, small=False):
    if not re.fullmatch(r"[a-f0-9]{40}",commit): raise ValueError("Pinned source commit required")
    source=Path("/opt/tak-orch/orchestrator/simulation-releases")/commit
    if (source/"simulation-source-commit").read_text().strip()!=commit: raise ValueError("Source marker mismatch")
    anchor=SEED_PATH.with_name("simulation-anchors.json")
    if not anchor.is_file() or anchor.stat().st_size>16384: raise ValueError("Bounded exercise anchors required")
    if SEED_PATH.is_symlink(): raise ValueError("Seed symlinks are not supported")
    if SEED_PATH.is_file():
        previous=SEED_PATH.with_name("simulation-state.previous-"+hashlib.sha256(SEED_PATH.read_bytes()).hexdigest()[:16]+".json")
        if not previous.exists():shutil.copy2(SEED_PATH,previous)
    script=('import sys,json,hashlib; from pathlib import Path; from takctl.simulation.orbat import build_hv_staging,build_group_staging; '
        'from takctl.simulation.daemon import atomic_json; '
        + ('state=build_group_staging(json.loads(Path(sys.argv[1]).read_text())["VQ"]); ' if small else 'state=build_hv_staging(json.loads(Path(sys.argv[1]).read_text())); ')
        +
        'target=Path(sys.argv[2]); atomic_json(target,state); target.chmod(0o640); '
        'print(json.dumps({"ok":True,"profile":state["orbat"]["profile"],"personnel":state["orbat"]["personnel"],'
        '"units":len(state["units"]),"markers":len(state["markers"]),"bytes":target.stat().st_size,'
        '"sha256":hashlib.sha256(target.read_bytes()).hexdigest(),"active":False}))')
    result=subprocess.run([sys.executable,"-c",script,str(anchor),str(SEED_PATH)],
        env=dict(os.environ,PYTHONPATH=str(source/"takctl")),capture_output=True,text=True,timeout=60,check=True)
    return json.loads(result.stdout)


def checkpoint_exercise():
    selected=json.loads(SEED_PATH.read_text())
    response=call("POST", "/api/v2/nodes/"+NODE+"/mcp/taks", {"jsonrpc":"2.0","id":1,"method":"tools/call",
        "params":{"name":"simulation_read","arguments":{"view":"export"}}})
    result=json.loads(response["result"]["content"][0]["text"])
    if not result.get("ok"): return result
    state=result["state"]
    if state.get("schema")!=1 or not isinstance(state.get("units"),dict): raise ValueError("Invalid exercise export")
    expected=selected.get("orbat",{}).get("instance_id")
    if expected and state.get("orbat",{}).get("instance_id")!=expected:
        raise ValueError("Live exercise does not match the selected roster instance")
    raw=json.dumps(state,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()
    if len(raw)>1048576: raise ValueError("Exercise exceeds the seed size limit")
    temp=SEED_PATH.with_suffix(".checkpoint.tmp")
    with temp.open("wb") as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    temp.chmod(0o640);os.replace(temp,SEED_PATH)
    fd=os.open(SEED_PATH.parent,os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return {"ok":True,"revision":state["revision"],"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),
            "personnel":sum(len(u["entities"]) for u in state["units"].values()),
            "active_personnel":sum(len(u["entities"]) for u in state["units"].values() if u["active"])}


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
    fragment=bootstrap / "simulation.conf"
    existing=dict(line.split("=",1) for line in fragment.read_text().splitlines() if "=" in line) if fragment.exists() else {}
    capacity=int(next((v.strip() for k,v in existing.items() if k.strip()=="simulation_identity_capacity"),"8"))
    if not 1<=capacity<=1024: raise ValueError("Invalid identity capacity")
    fragment.write_text("simulation_enabled = true\nsimulation_identity_capacity = "+str(capacity)+"\n")
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
    found = {};seed_slots=[]
    with tarfile.open(archive, "r|gz") as tar:
        for member in tar:
            for suffix in expected:
                if member.name == suffix or member.name.endswith("/"+suffix):
                    if not member.isfile():
                        raise ValueError("MVP bundle member is not a file")
                    found[suffix] = True
                    if suffix == seed_key:
                        if member.size > 1048576: raise ValueError("Exercise seed too large")
                        raw=tar.extractfile(member).read()
                        found[suffix] = hashlib.sha256(raw).hexdigest()
                        state=json.loads(raw)
                        seed_slots=[e["identity_slot"] for u in state["units"].values() for e in u["entities"]]
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
    values=dict(line.split("=",1) for line in found[config_key].splitlines() if "=" in line)
    capacity=int(next((v.strip() for k,v in values.items() if k.strip()=="simulation_identity_capacity"),"8"))
    if not 1<=capacity<=1024 or (seed_slots and max(seed_slots)>=capacity):
        return {"ok":False,"error":"Bundle identity capacity cannot serve its exercise seed"}
    return {"ok":True,"bundle":"taklabs.tar.gz","bytes":after.st_size,
            "source_commit":found[commit_key],"simulation_enabled":True,"checked_files":len(found),"exercise_seed_verified":bool(seed_hash),
            "identity_capacity":capacity,"seed_personnel":len(seed_slots)}


def qos_delivery(apply=False):
    # Fixed exercise node and fixed admin endpoints; no URL or credential inputs.
    import ssl
    inventory = call("GET", "/api/v2/nodes")
    matches = [n for n in inventory.get("items", []) if n.get("node_id")==NODE]
    if len(matches)!=1 or matches[0].get("unit_path")!=UNIT or matches[0].get("fqdn")!=NODE:
        raise ValueError("Exercise node registry mismatch")
    def values(kind):
        result = {}
        for root in (Path("/opt/tak-orch/state/bootstrap"), Path("/opt/tak-orch/state/units/taklabs/bootstrap")):
            for path in sorted((root/kind).rglob("*.conf")):
                if path.is_symlink(): raise ValueError("Bootstrap symlink rejected")
                for raw in path.read_text().splitlines():
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line: continue
                    key,value = line.split("=",1)
                    result[key.strip()] = value.strip()
        return result
    cfg, secret = values("config.d"), values("secrets.d")
    username = str(cfg.get("takctl_admin_user") or "admin").strip()
    password = str(secret.get("takctl_admin_password") or "").strip()
    if not password: raise ValueError("Installer admin unavailable")
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl): return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
        NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    login = urllib.request.Request("https://"+NODE+":8446/oauth/token", method="POST",
        data=urllib.parse.urlencode({"grant_type":"password","username":username,"password":password}).encode(),
        headers={"Content-Type":"application/x-www-form-urlencoded"})
    with opener.open(login,timeout=10) as response:
        raw = response.read(65537)
        if len(raw)>65536: raise ValueError("OAuth response too large")
        auth = json.loads(raw)
    token = str(auth.get("access_token") or "")
    if not token or str(auth.get("token_type","Bearer")).lower()!="bearer":
        raise ValueError("Invalid OAuth response")
    def request(method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request("https://"+NODE+":8446/Marti/api/qos/"+path,
            data=data,method=method,headers={"Accept":"application/json","Content-Type":"application/json","Authorization":"Bearer "+token})
        with opener.open(req,timeout=10) as response:
            raw = response.read(65537)
            if len(raw)>65536: raise ValueError("QoS response too large")
            return json.loads(raw) if raw else {"http_status":response.status}
    conf = request("GET","conf")
    conf = conf.get("data", conf)
    before = request("GET","ratelimit/delivery/active")
    if not apply: return {"ok":True,"configuration":conf,"active_delivery":before}
    limiter = conf.get("deliveryRateLimiter", {})
    rules = limiter.get("rateLimitRule")
    if not limiter.get("enabled") or not isinstance(rules,list):
        raise ValueError("Expected enabled delivery limiter")
    updated = [dict(rule) for rule in rules]
    selected = [rule for rule in updated if rule.get("clientThresholdCount")==500]
    if len(selected)!=1: raise ValueError("Expected one 500-client delivery rule")
    selected[0]["reportingRateLimitSeconds"] = 10
    saved = Path("/opt/tak-orch/state/units/taklabs/simulation-qos.previous.json")
    if not saved.exists():
        saved.write_text(json.dumps(conf));saved.chmod(0o600)
    request("PUT","delivery/set",updated)
    return {"ok":True,"previous_active_delivery":before,
        "active_delivery":request("GET","ratelimit/delivery/active"),
        "configuration":request("GET","conf")}


def compare_exercise_resources():
    """Read-only snapshots and recent EC2 CPU metrics for the two lab nodes."""
    from datetime import datetime, timedelta, timezone
    inventory = call("GET", "/api/v2/nodes")
    results = []
    for node_id in (NODE, "takdiag.aws.tak-hv-sandbox.se"):
        matches = [n for n in inventory.get("items", []) if n.get("node_id") == node_id]
        if len(matches) != 1:
            results.append({"node":node_id,"error":"Node not uniquely registered"}); continue
        node = matches[0]
        row = {"node":node_id,"instance_type":node.get("meta",{}).get("instance_type")}
        for key, operation in (("host","host_resources"),("tak","takserver_readiness")):
            response = call("POST", "/api/v2/nodes/"+node_id+"/mcp/devops", {
                "jsonrpc":"2.0","id":1,"method":"tools/call",
                "params":{"name":operation,"arguments":{}}})
            try: row[key] = json.loads(response["result"]["content"][0]["text"])
            except (KeyError,IndexError,ValueError): row[key] = {"error":"Node diagnostics unavailable"}
        identity = node.get("aws_instance_id", "")
        if re.fullmatch(r"i-[0-9a-f]{8,17}", identity):
            end = datetime.now(timezone.utc)
            args = ["aws","cloudwatch","get-metric-statistics","--region","eu-north-1",
                "--namespace","AWS/EC2","--metric-name","CPUUtilization",
                "--dimensions","Name=InstanceId,Value="+identity,
                "--start-time",(end-timedelta(minutes=30)).isoformat(),"--end-time",end.isoformat(),
                "--period","300","--statistics","Average","Maximum","--output","json"]
            try:
                result = subprocess.run(args,capture_output=True,text=True,timeout=15)
                if result.returncode:
                    row["ec2_cpu"] = {"error":"CloudWatch read failed","access_denied":"AccessDenied" in result.stderr}
                else:
                    metrics = json.loads(result.stdout)
                    row["ec2_cpu"] = {"period_seconds":300,"unit":metrics.get("Datapoints",[{}])[0].get("Unit"),
                        "datapoints":sorted(metrics.get("Datapoints",[]),key=lambda p:p["Timestamp"])[-3:]}
            except (OSError,ValueError,subprocess.TimeoutExpired):
                row["ec2_cpu"] = {"error":"CloudWatch read unavailable"}
        results.append(row)
    return {"ok":True,"nodes":results}


def exercise_instance_type(capacity):
    if type(capacity) is not int or not 1<=capacity<=1024: raise ValueError("Invalid identity capacity")
    return "t3.medium" if capacity<=256 else "t3.large" if capacity<=640 else "t3.xlarge"


def dispatch_release(command):
    p = command.split() if isinstance(command, str) and len(command) < 400 else []
    if len(p) < 2 or p[0] != "taks-release":
        return {"ok": False, "error": "Invalid release command"}
    try:
        op = p[1]
        tools = lifecycle()
        if op == "monitor" and len(p)==4 and p[2] in ("orchestrator",UNIT,"takdiag") and p[3] in ("top","memory","vmstat"):
            from app import host_monitor
            operation={"top":"process_sample","memory":"memory_read","vmstat":"vmstat_sample"}[p[3]]
            if p[2]=="orchestrator":
                return host_monitor.sample_snapshot() if p[3]=="top" else host_monitor.memory_snapshot() if p[3]=="memory" else host_monitor.vmstat_samples()
            node=NODE if p[2]==UNIT else "takdiag.aws.tak-hv-sandbox.se"
            return call("POST","/api/v2/nodes/"+node+"/mcp/devops",{
                "jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":operation,"arguments":{}}})
        if op == "compare-resources" and p[2:] == [UNIT]:
            return submit(("compare-resources",UNIT),compare_exercise_resources)
        if op == "qos" and p[2:] == [UNIT]:
            return qos_delivery(False)
        if op == "qos-ten-seconds" and p[2:] == [UNIT,"confirm"]:
            return qos_delivery(True)
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
        if op == "web-logs" and p[2:] == [UNIT]:
            return call("POST", "/api/v2/nodes/"+NODE+"/mcp/devops", {
                "jsonrpc":"2.0", "id":1, "method":"tools/call", "params": {
                    "name":"service_logs", "arguments":{"service":"takctl-web.service","lines":80}}})
        if op in ("tak-diagnostics", "tak-logs") and p[2:] == [UNIT]:
            name = "takserver_readiness" if op == "tak-diagnostics" else "takserver_logs"
            return call("POST", "/api/v2/nodes/"+NODE+"/mcp/devops", {
                "jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":name,"arguments":{}}})
        if op == "tak-log" and len(p)==4 and p[2]==UNIT and p[3] in ("messaging","api","config"):
            name = {"messaging":"takserver-messaging.log","api":"takserver-api.log","config":"takserver-config.log"}[p[3]]
            return call("POST", "/api/v2/nodes/"+NODE+"/mcp/devops", {
                "jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"takserver_logs","arguments":{"file":name,"lines":80}}})
        if op == "resources" and p[2:] == [UNIT]:
            return call("POST", "/api/v2/nodes/"+NODE+"/mcp/devops", {
                "jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"host_resources","arguments":{}}})
        if op == "checkpoint" and p[2:] == [UNIT,"confirm"]:
            return submit(("checkpoint",UNIT),checkpoint_exercise)
        if op == "map-probe" and p[2:] == [UNIT]:
            return submit(("map-probe",UNIT),map_upstream_probe)
        if op == "map-bbox" and p[2:] == [UNIT]:
            return submit(("map-bbox",UNIT),map_bbox_probe)
        if op == "identities" and len(p)==5 and p[2]==UNIT and p[4]=="confirm" and p[3].isdigit() and 1<=int(p[3])<=1024:
            fragment=Path("/opt/tak-orch/state/units/taklabs/bootstrap/config.d/simulation.conf")
            fragment.write_text("simulation_enabled = true\nsimulation_identity_capacity = "+p[3]+"\n")
            return {"ok":True,"unit":UNIT,"next_boot_identity_capacity":int(p[3]),"running_node_changed":False}
        if op == "prepare-roster" and len(p)==5 and p[2]==UNIT and p[4]=="confirm" and re.fullmatch(r"[a-f0-9]{40}",p[3]):
            return submit(("prepare-roster",UNIT),lambda:prepare_staging_roster(p[3]))
        if op == "prepare-group" and len(p)==5 and p[2]==UNIT and p[4]=="confirm" and re.fullmatch(r"[a-f0-9]{40}",p[3]):
            return submit(("prepare-group",UNIT),lambda:prepare_staging_roster(p[3],True))
        if op == "shutdown" and len(p) == 6 and p[2] == NODE and p[5] == "confirm":
            return tools["taks_node_shutdown"](NODE,UNIT,p[3],p[4],True)
        if op == "launch" and p[2:] == [UNIT,"confirm"]:
            fragment=Path("/opt/tak-orch/state/units/taklabs/bootstrap/config.d/simulation.conf")
            settings=dict(line.split("=",1) for line in fragment.read_text().splitlines() if "=" in line)
            capacity=int(next((v.strip() for k,v in settings.items() if k.strip()=="simulation_identity_capacity"),"8"))
            if not 1<=capacity<=1024: raise ValueError("Invalid identity capacity")
            return tools["taks_node_launch_start"](UNIT,NODE,exercise_instance_type(capacity),True)
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
