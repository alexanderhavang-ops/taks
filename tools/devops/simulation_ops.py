"""Restricted MVP deployment dispatch. No user-supplied shell or file paths.

Called by the existing DevOps command entry point while arbitrary shell stays
disabled. Source installation accepts only pinned commits of the TAKS repo.
"""
import json
import re
import subprocess
from app.cert_ops_component import remote, run
from app.route53_component import _node_context, _ec2_ip

SHA = re.compile(r"[a-f0-9]{40}\Z")
NODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
COMMAND = re.compile(r"[a-f0-9-]{36}\Z")

INSPECT = r'''python3 - <<'PY'
import json,pathlib,subprocess
root=pathlib.Path('/opt/tak/simulation')
out={'simulation_installed':(root/'config.json').exists()}
if (root/'config.json').exists():
    cfg=json.loads((root/'config.json').read_text())
    out.update(source_commit=cfg.get('source_commit'),identity_capacity=len(cfg.get('identities',[])))
for service in ('takctl-web.service','taks-simulation.service'):
    p=subprocess.run(['systemctl','show',service,'--property=ActiveState,MainPID,MemoryCurrent,TasksCurrent','--no-pager'],capture_output=True,text=True)
    out[service]=p.stdout.strip()
out['map_paths']={p:pathlib.Path(p).exists() for p in ('/opt/tak/geo/osm-tiles','/opt/tak/tools/takctl/state/docs/registry/docs.json')}
domain=pathlib.Path('/opt/tak/tools/takctl/takctl/web/mcp_domains/taks.py')
out['business_module_bytes']=domain.stat().st_size if domain.exists() else None
print(json.dumps(out))
PY'''


def dispatch_mvp(command):
    if not isinstance(command, str) or len(command) > 300:
        return {"ok": False, "error": "Invalid MVP operation"}
    parts = command.split()
    try:
        if parts == ["taks-mvp", "reload-orchestrator"]:
            results = []
            for service in ("taks-orch.service", "taks-business-mcp.service"):
                results.append(run(["/usr/bin/sudo", "-n", "/usr/bin/systemctl", "restart", service]))
            return {"ok": all(r.get("ok") for r in results), "services": results}
        if len(parts) < 3 or parts[0] != "taks-mvp" or not NODE.fullmatch(parts[2]):
            raise ValueError("Expected taks-mvp inspect/deploy/poll NODE [SHA/COMMAND_ID]")
        op, node_id = parts[1:3]
        if op == "inspect" and len(parts) == 3:
            return remote(node_id, INSPECT)
        if op not in ("deploy", "poll") or len(parts) != 4:
            raise ValueError("Unsupported MVP operation")
        if op == "deploy" and not SHA.fullmatch(parts[3]):
            raise ValueError("Pinned lowercase commit SHA required")
        if op == "poll" and not COMMAND.fullmatch(parts[3]):
            raise ValueError("Invalid SSM command ID")
        node, _, region, _, instance = _node_context(node_id)
        _ec2_ip(region, instance, str(node["unit_path"]))
        if op == "poll":
            if not COMMAND.fullmatch(parts[3]):
                raise ValueError("Invalid SSM command ID")
            result = run(["/usr/bin/aws", "ssm", "get-command-invocation", "--region", region,
                "--instance-id", instance, "--command-id", parts[3], "--output", "json"])
            if not result.get("ok"):
                return result
            data = json.loads(result["stdout"])
            return {"ok": data.get("Status") == "Success", "status": data.get("Status"),
                    "stdout": data.get("StandardOutputContent", "")[:4000],
                    "stderr": data.get("StandardErrorContent", "")[:2000]}
        sha = parts[3]
        # Fixed repository, script and arguments; no arbitrary command dispatch.
        script = ("import pathlib,urllib.request,subprocess; "
                  "u='https://raw.githubusercontent.com/alexanderhavang-ops/taks/" + sha + "/tools/deploy-simulation-mvp.py'; "
                  "p=pathlib.Path('/var/tmp/taks-deploy-simulation-" + sha + ".py'); "
                  "p.write_bytes(urllib.request.urlopen(u,timeout=30).read(200000)); "
                  "subprocess.run(['python3',str(p),'--commit','" + sha + "'],check=True)")
        import shlex
        sent = run(["/usr/bin/aws", "ssm", "send-command", "--region", region,
            "--instance-ids", instance, "--document-name", "AWS-RunShellScript",
            "--parameters", json.dumps({"commands": ["python3 -c " + shlex.quote(script)], "executionTimeout": ["300"]}),
            "--query", "Command.CommandId", "--output", "text"])
        if not sent.get("ok"):
            return sent
        return {"ok": True, "status": "submitted", "node_id": node_id,
                "command_id": sent["stdout"].strip(), "commit": sha}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}
