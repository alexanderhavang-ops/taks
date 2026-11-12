"""Scoped Certbot and node maintenance MCP operations."""
import json
import re
import subprocess
import time
from app.route53_component import _node_context, _ec2_ip, DNSFailure

SERVICES = frozenset(("nginx.service", "takserver.service", "takctl-web.service", "martine-cot.service"))

def run(argv, timeout=30):
    try:
        p = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
        return {"ok": p.returncode == 0, "exit_code": p.returncode,
                "stdout": p.stdout[:6000].decode(errors="replace"),
                "stderr": p.stderr[:1000].decode(errors="replace")}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": type(exc).__name__}

def remote(node_id, command):
    try:
        node, _, region, _, instance = _node_context(node_id)
        _ec2_ip(region, instance, str(node["unit_path"]))
        found = run(["/usr/bin/aws", "ssm", "describe-instance-information",
                     "--region", region, "--filters", "Key=InstanceIds,Values=" + instance,
                     "--output", "json"])
        if not found["ok"]:
            return {"ok": False, "error": "SSM lookup failed", "detail": found["stderr"]}
        entries = json.loads(found["stdout"]).get("InstanceInformationList", [])
        if len(entries) != 1 or entries[0].get("InstanceId") != instance or entries[0].get("PingStatus") != "Online":
            return {"ok": False, "error": "Registered node is not online in SSM"}
        sent = run(["/usr/bin/aws", "ssm", "send-command", "--region", region,
                    "--instance-ids", instance, "--document-name", "AWS-RunShellScript",
                    "--parameters", json.dumps({"commands": [command], "executionTimeout": ["60"]}),
                    "--query", "Command.CommandId", "--output", "text"])
        if not sent["ok"]:
            return {"ok": False, "error": "SSM send failed", "detail": sent["stderr"]}
        cid = sent["stdout"].strip()
        if not re.fullmatch(r"[a-f0-9-]{36}", cid):
            return {"ok": False, "error": "Invalid SSM command ID"}
        for _ in range(15):
            time.sleep(2)
            result = run(["/usr/bin/aws", "ssm", "get-command-invocation",
                          "--region", region, "--instance-id", instance,
                          "--command-id", cid, "--output", "json"])
            if not result["ok"]:
                continue
            payload = json.loads(result["stdout"])
            if payload.get("Status") in ("Pending", "InProgress", "Delayed"):
                continue
            return {"ok": payload.get("Status") == "Success", "node_id": node_id,
                    "command_id": cid, "status": payload.get("Status"),
                    "stdout": str(payload.get("StandardOutputContent", ""))[:4000],
                    "stderr": str(payload.get("StandardErrorContent", ""))[:1000]}
        return {"ok": False, "command_id": cid, "error": "SSM still pending"}
    except (DNSFailure, ValueError, KeyError) as exc:
        return {"ok": False, "error": str(exc)[:300]}

def register_cert_ops_tools(mcp):
    @mcp.tool()
    def certbot_status() -> dict:
        """Show locally configured certificate lineages."""
        return run(["/usr/bin/sudo", "-n", "/usr/bin/certbot", "certificates"])

    @mcp.tool()
    def certbot_renew(dry_run: bool = True, confirm_renew: bool = False) -> dict:
        """Dry-run or explicitly approve Certbot renewal."""
        if not dry_run and not confirm_renew:
            return {"ok": False, "confirmation_required": True}
        argv = ["/usr/bin/sudo", "-n", "/usr/bin/certbot", "renew", "--non-interactive"]
        if dry_run:
            argv.append("--dry-run")
        return run(argv, 90)

    @mcp.tool()
    def node_certbot_status(node_id: str) -> dict:
        """Inspect Certbot on a registered SSM node."""
        return remote(node_id, "certbot certificates")

    @mcp.tool()
    def node_certbot_renew(node_id: str, dry_run: bool = True, confirm_renew: bool = False) -> dict:
        """Renew existing node certificate lineages; dry-run by default."""
        if not dry_run and not confirm_renew:
            return {"ok": False, "confirmation_required": True}
        return remote(node_id, "certbot renew --non-interactive" + (" --dry-run" if dry_run else ""))

    @mcp.tool()
    def node_nginx_config_check(node_id: str) -> dict:
        """Validate Nginx on a registered node."""
        return remote(node_id, "nginx -t")

    @mcp.tool()
    def node_nginx_reload(node_id: str, confirm_reload: bool = False) -> dict:
        """Validate Nginx and reload after explicit approval."""
        if not confirm_reload:
            return {"ok": False, "confirmation_required": True}
        return remote(node_id, "nginx -t && systemctl reload nginx.service")

    @mcp.tool()
    def node_systemd_status(node_id: str, service: str) -> dict:
        """Read status for one allowlisted node service."""
        if service not in SERVICES:
            return {"ok": False, "error": "Service not allowed"}
        return remote(node_id, "systemctl show " + service + " --property=ActiveState,SubState,Result,MainPID --no-pager")

    @mcp.tool()
    def node_systemd_restart(node_id: str, service: str, confirm_restart: bool = False) -> dict:
        """Restart an allowlisted node service with explicit approval."""
        if service not in SERVICES:
            return {"ok": False, "error": "Service not allowed"}
        if not confirm_restart:
            return {"ok": False, "confirmation_required": True}
        return remote(node_id, "systemctl restart " + service)
