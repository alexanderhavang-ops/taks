"""Scoped Route 53 inspection and repair for registered TAKS node DNS.

Only the hosted zone and node domain configured on the orchestrator are accepted.
Repairs derive the destination IPv4 address from the running EC2 instance,
never from user-supplied values or the possibly stale node registry.
"""
from __future__ import annotations

import ipaddress
import json
import re
import subprocess
from pathlib import Path

from app.orchestrator_component import call

CONFIG = Path("/opt/tak-orch/orchestrator/conf.d/core.conf")
AWS = "/usr/bin/aws"
INSTANCE_ID = re.compile(r"i-[0-9a-f]{8,17}\Z")
ZONE_ID = re.compile(r"Z[A-Z0-9]{8,32}\Z")
REGION = re.compile(r"[a-z]{2}-[a-z0-9-]+-\d\Z")
DNS_NAME = re.compile(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\Z")
NODE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


class DNSFailure(Exception):
    pass


def _config():
    if CONFIG.is_symlink():
        raise DNSFailure("Orchestrator config is a symlink")
    try:
        lines = CONFIG.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise DNSFailure("Orchestrator DNS config unavailable") from exc
    cfg = {}
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        cfg[key.strip()] = value.strip().strip('"').strip("'")
    zone, region, domain = (cfg.get(k, "") for k in (
        "aws_route53_zone_id", "aws_region", "nodes_default_node_domain"))
    domain = domain.lower().strip(".")
    if (not ZONE_ID.fullmatch(zone) or not REGION.fullmatch(region)
            or not DNS_NAME.fullmatch(domain) or "." not in domain or ".." in domain):
        raise DNSFailure("Invalid or missing configured Route 53 zone, region or node domain")
    return zone, region, domain


def _aws(*args, timeout=25):
    try:
        result = subprocess.run([AWS, *args, "--output", "json"],
                                stdin=subprocess.DEVNULL, capture_output=True,
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DNSFailure(f"AWS command unavailable: {type(exc).__name__}") from exc
    if result.returncode:
        message = result.stderr.decode("utf-8", "replace")[:300]
        raise DNSFailure("AWS API failed: " + message.strip())
    try:
        return json.loads(result.stdout)
    except (ValueError, UnicodeError) as exc:
        raise DNSFailure("AWS response is not valid JSON") from exc


def _registered_node(node_id):
    if not isinstance(node_id, str) or not NODE_ID.fullmatch(node_id):
        raise DNSFailure("Invalid node ID")
    inventory = call("GET", "/api/v2/nodes")
    if not isinstance(inventory, dict) or inventory.get("ok") is False:
        raise DNSFailure("Orchestrator node inventory unavailable")
    matches = [n for n in inventory.get("items", [])
               if isinstance(n, dict) and n.get("node_id") == node_id]
    if len(matches) != 1:
        raise DNSFailure("Node is not uniquely registered; orphaned nodes cannot be repaired")
    return matches[0]


def _node_context(node_id):
    node = _registered_node(node_id)
    zone_id, region, domain = _config()
    fqdn = str(node.get("fqdn") or "").lower().strip(".")
    instance_id = str(node.get("aws_instance_id") or "").strip()
    unit = str(node.get("unit_path") or "").strip()
    if (not DNS_NAME.fullmatch(fqdn) or ".." in fqdn
            or not fqdn.endswith("." + domain) or not INSTANCE_ID.fullmatch(instance_id)
            or not unit):
        raise DNSFailure("Registered node FQDN or instance ID invalid")
    zone_info = _aws("route53", "get-hosted-zone", "--id", zone_id)
    hosted_zone = str((zone_info.get("HostedZone") or {}).get("Name") or "").lower().strip(".")
    if not hosted_zone or not fqdn.endswith("." + hosted_zone):
        raise DNSFailure("Node FQDN is outside configured hosted zone")
    return node, zone_id, region, fqdn, instance_id


def _record(zone_id, name):
    result = _aws("route53", "list-resource-record-sets",
                  "--hosted-zone-id", zone_id, "--start-record-name", name,
                  "--start-record-type", "A", "--max-items", "1")
    for item in result.get("ResourceRecordSets", [])[:1]:
        if (str(item.get("Name") or "").lower().rstrip(".") == name
                and item.get("Type") == "A"):
            return {
                "name": name,
                "ttl": item.get("TTL"),
                "addresses": [r.get("Value") for r in item.get("ResourceRecords", [])],
                "alias": bool(item.get("AliasTarget")),
            }
    return {"name": name, "ttl": None, "addresses": [], "alias": False}


def _ec2_ip(region, instance_id, unit):
    result = _aws("ec2", "describe-instances", "--region", region,
                  "--instance-ids", instance_id,
                  "--query", "Reservations[0].Instances[0]")
    if not isinstance(result, dict) or result.get("InstanceId") != instance_id:
        raise DNSFailure("EC2 instance not found")
    state = str((result.get("State") or {}).get("Name") or "")
    if state != "running":
        raise DNSFailure(f"EC2 instance not running: {state or 'unknown'}")
    tags = {t.get("Key"): t.get("Value") for t in result.get("Tags", [])
            if isinstance(t, dict)}
    if tags.get("taks.unit_path") != unit or tags.get("taks.role") != "tak-node":
        raise DNSFailure("EC2 instance tags do not match registered TAKS node")
    ip = str(result.get("PublicIpAddress") or "")
    try:
        if not ipaddress.IPv4Address(ip).is_global:
            raise DNSFailure("EC2 does not have a public IPv4 address")
    except ipaddress.AddressValueError as exc:
        raise DNSFailure("Invalid EC2 public IPv4 address") from exc
    return ip


def _status(node_id):
    node, zone, region, fqdn, instance_id = _node_context(node_id)
    ip = _ec2_ip(region, instance_id, str(node["unit_path"]))
    names = (fqdn, "devops." + fqdn)
    records = {name: _record(zone, name) for name in names}
    synced = all(not records[name]["alias"] and records[name]["addresses"] == [ip]
                 for name in names)
    return {
        "ok": True,
        "node_id": node_id,
        "hosted_zone_id": zone,
        "instance_id": instance_id,
        "ec2_public_ip": ip,
        "records": records,
        "in_sync": synced,
    }


def status(node_id):
    try:
        return _status(node_id)
    except DNSFailure as exc:
        return {"ok": False, "node_id": node_id, "error": str(exc)[:400]}


def repair(node_id):
    try:
        current = _status(node_id)
        if current["in_sync"]:
            return {**current, "changed": False}
        if any(item["alias"] for item in current["records"].values()):
            raise DNSFailure("Unexpected Route 53 alias record; manual review required")
        change_batch = {
            "Comment": f"TAKS DevOps repair for {node_id}",
            "Changes": [
                {"Action": "UPSERT", "ResourceRecordSet": {
                    "Name": name, "Type": "A", "TTL": 60,
                    "ResourceRecords": [{"Value": current["ec2_public_ip"]}],
                }}
                for name in current["records"]
            ],
        }
        result = _aws("route53", "change-resource-record-sets",
                      "--hosted-zone-id", current["hosted_zone_id"],
                      "--change-batch", json.dumps(change_batch))
        change = result.get("ChangeInfo") or {}
        return {**current, "ok": True, "changed": True,
                "change_id": change.get("Id"), "change_status": change.get("Status")}
    except DNSFailure as exc:
        return {"ok": False, "node_id": node_id, "error": str(exc)[:400]}


def register_route53_tools(mcp):
    @mcp.tool()
    def route53_node_dns_status(node_id: str) -> dict:
        """Read node and devops.<node> A records against the actual running EC2 IP."""
        return status(node_id)

    @mcp.tool()
    def route53_node_dns_repair(node_id: str, confirm_repair: bool = False) -> dict:
        """Repair the two TAKS node A records using the instance's AWS-verified IP."""
        if not confirm_repair:
            return {"ok": False, "node_id": node_id, "confirmation_required": True}
        return repair(node_id)
