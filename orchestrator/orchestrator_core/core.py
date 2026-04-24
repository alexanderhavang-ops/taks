from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import boto3
import yaml
from orchestrator_core.config import load_orch_config
from jinja2 import Environment, FileSystemLoader, StrictUndefined


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = REPO_ROOT / "orchestrator" / "templates"


def region() -> str:
    cfg = load_orch_config()
    return cfg.aws.region


def jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )


def render_cloud_init(*, unit_path: str, role: str, fqdn: str, hostname: str) -> str:
    """
    Render cloud-init for a node.

    Template-driven so WebUI / CLI / API stay consistent.
    Cloud-init is intentionally super-KISS: download rendered unit bundle and run startup.sh.
    """
    cfg = load_orch_config()
    orch_api_url = cfg.identity.public_base_url

    tpl = jinja_env().get_template("tak-node.cloud-init.yml.j2")
    return tpl.render(
        unit_path=unit_path,
        role=role,
        fqdn=fqdn,
        hostname=hostname,
        orch_api_url=orch_api_url,
    )


def validate_cloud_init(text: str) -> None:
    if not text.lstrip().startswith("#cloud-config"):
        raise ValueError("cloud-init must start with #cloud-config")
    yaml.safe_load(text)  # raises on invalid yaml


def resolve_ubuntu_ami(*, region_name: str) -> str:
    cfg = load_orch_config()

    pinned = str(cfg.aws.default_ami or "").strip()
    if pinned:
        return pinned

    ec2 = boto3.client("ec2", region_name=region_name)
    resp = ec2.describe_images(
        Owners=["099720109477"],
        Filters=[
            {
                "Name": "name",
                "Values": ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"],
            }
        ],
    )
    images = list(resp.get("Images") or [])
    if not images:
        raise RuntimeError(
            f"no Canonical Ubuntu 24.04 images found in region {region_name}"
        )

    images.sort(key=lambda x: str(x.get("CreationDate") or ""))
    ami = str(images[-1].get("ImageId") or "").strip()
    if not ami:
        raise RuntimeError(
            f"latest Canonical Ubuntu 24.04 image in region {region_name} had empty ImageId"
        )
    return ami


def resolve_default_public_subnet(*, region_name: str) -> Dict[str, str]:
    cfg = load_orch_config()
    return {"vpc_id": "configured", "subnet_id": cfg.aws.default_subnet_id}


@dataclass
class NodeRequest:
    # Identity
    unit_path: str
    role: str

    # Node basics
    fqdn: str = ""
    hostname: str = ""
    name: str = ""
    instance_type: str = "t3.micro"

    # Optional AWS overrides
    aws_key_name: str | None = None
    aws_sg_id: str | None = None

    # Bundle naming
    bundle_name: str | None = None
    bundle_ttl: int | None = None
def plan_node(req: NodeRequest) -> Dict[str, Any]:
    r = region()
    ami = resolve_ubuntu_ami(region_name=r)
    net = resolve_default_public_subnet(region_name=r)

    ci = render_cloud_init(
        unit_path=req.unit_path,
        role=req.role,
        fqdn=req.fqdn,
        hostname=req.hostname,
    )
    validate_cloud_init(ci)

    return {
        "region": r,
        "ami": ami,
        "vpc_id": net["vpc_id"],
        "subnet_id": net["subnet_id"],
        "instance_type": req.instance_type,
        "tags": {
            "Name": req.name,
            "taks.role": req.role,
            "taks.unit_path": req.unit_path,
        },
        "cloud_init": ci,
    }


def aws_dry_run(req: NodeRequest) -> Dict[str, Any]:
    plan = plan_node(req)
    return {
        "dry_run_ok": True,
        "plan": {
            "region": plan["region"],
            "ami": plan["ami"],
            "vpc_id": plan["vpc_id"],
            "subnet_id": plan["subnet_id"],
            "instance_type": plan["instance_type"],
            "tags": plan["tags"],
        },
    }


def _route53_zone_id() -> str:
    cfg = load_orch_config()
    return str(cfg.aws.route53_zone_id).strip()


def _wait_for_instance_network(ec2, instance_id: str, *, timeout_seconds: int = 300, sleep_seconds: int = 5) -> Dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last: Dict[str, Any] = {}

    while time.time() < deadline:
        resp = ec2.describe_instances(InstanceIds=[instance_id])
        reservations = list(resp.get("Reservations") or [])
        inst = {}
        if reservations and reservations[0].get("Instances"):
            inst = dict(reservations[0]["Instances"][0] or {})
            last = inst

        public_ip = str(inst.get("PublicIpAddress") or "").strip()
        private_ip = str(inst.get("PrivateIpAddress") or "").strip()
        state = str(((inst.get("State") or {}).get("Name")) or "").strip()

        if private_ip and public_ip:
            return inst

        if state in {"shutting-down", "terminated"}:
            raise RuntimeError(f"instance {instance_id} entered state {state} before network became ready")

        time.sleep(sleep_seconds)

    raise RuntimeError(
        f"timed out waiting for instance network info for {instance_id}; "
        f"last_state={((last.get('State') or {}).get('Name') or '')} "
        f"last_private_ip={last.get('PrivateIpAddress') or ''} "
        f"last_public_ip={last.get('PublicIpAddress') or ''}"
    )


def _upsert_node_dns(*, zone_id: str, fqdn: str, public_ip: str, ttl: int = 60) -> Dict[str, Any]:
    fqdn = str(fqdn or "").strip().rstrip(".")
    public_ip = str(public_ip or "").strip()
    if not zone_id:
        raise RuntimeError("missing route53 zone id")
    if not fqdn:
        raise RuntimeError("missing fqdn for dns upsert")
    if not public_ip:
        raise RuntimeError("missing public_ip for dns upsert")

    r53 = boto3.client("route53")
    change_batch = {
        "Comment": f"TAKS node DNS upsert for {fqdn}",
        "Changes": [
            {
                "Action": "UPSERT",
                "ResourceRecordSet": {
                    "Name": fqdn,
                    "Type": "A",
                    "TTL": ttl,
                    "ResourceRecords": [{"Value": public_ip}],
                },
            }
        ],
    }

    resp = r53.change_resource_record_sets(
        HostedZoneId=zone_id,
        ChangeBatch=change_batch,
    )
    return dict(resp.get("ChangeInfo") or {})


def aws_launch(req: NodeRequest) -> Dict[str, Any]:
    r = region()
    plan = plan_node(req)

    cfg = load_orch_config()
    sg_id = (req.aws_sg_id or cfg.aws.default_security_group_id or "").strip()
    key_name = (req.aws_key_name or cfg.aws.ssh_key_name or "").strip()
    instance_profile = str(getattr(cfg.aws, "default_instance_profile", "") or "").strip()

    if not sg_id:
        raise RuntimeError("Missing security group id (set aws.default_security_group_id or pass aws_sg_id)")
    if not key_name:
        raise RuntimeError("Missing EC2 keypair name (set aws.ssh_key_name or pass aws_key_name)")

    ec2 = boto3.client("ec2", region_name=r)

    kwargs: Dict[str, Any] = {
        "ImageId": plan["ami"],
        "InstanceType": plan["instance_type"],
        "KeyName": key_name,
        "MinCount": 1,
        "MaxCount": 1,
        "NetworkInterfaces": [
            {
                "DeviceIndex": 0,
                "SubnetId": plan["subnet_id"],
                "Groups": [sg_id],
                "AssociatePublicIpAddress": True,
            }
        ],
        "UserData": plan["cloud_init"],
        "BlockDeviceMappings": [
            {
                "DeviceName": "/dev/sda1",
                "Ebs": {
                    "VolumeSize": 64,
                    "VolumeType": "gp3",
                    "DeleteOnTermination": True,
                },
            }
        ],
        "TagSpecifications": [
            {
                "ResourceType": "instance",
                "Tags": [{"Key": k, "Value": str(v)} for k, v in plan["tags"].items()],
            }
        ],
    }


    resp = ec2.run_instances(**kwargs)
    inst = resp["Instances"][0]
    instance_id = str(inst["InstanceId"])

    inst_live = _wait_for_instance_network(ec2, instance_id)
    public_ip = str(inst_live.get("PublicIpAddress") or "").strip()
    private_ip = str(inst_live.get("PrivateIpAddress") or "").strip()
    state = str(((inst_live.get("State") or {}).get("Name")) or inst["State"]["Name"]).strip()

    zone_id = _route53_zone_id()
    dns_change = None
    if zone_id:
        dns_change = _upsert_node_dns(
            zone_id=zone_id,
            fqdn=req.fqdn,
            public_ip=public_ip,
        )

    return {
        "instance_id": instance_id,
        "state": state,
        "region": r,
        "subnet_id": plan["subnet_id"],
        "sg_id": sg_id,
        "private_ip": private_ip,
        "public_ip": public_ip,
        "fqdn": req.fqdn,
        "route53_zone_id": zone_id or None,
        "dns_change": dns_change,
    }



def aws_snooze(instance_id: str, *, fqdn: str = "") -> Dict[str, Any]:
    iid = str(instance_id or "").strip()
    fqdn = str(fqdn or "").strip()
    if not iid:
        raise ValueError("missing instance_id")

    r = region()
    ec2 = boto3.client("ec2", region_name=r)
    resp = ec2.stop_instances(InstanceIds=[iid])

    items = list(resp.get("StoppingInstances") or [])
    row = items[0] if items else {}

    zone_id = _route53_zone_id()
    dns_change = None
    if zone_id and fqdn:
        dns_change = _upsert_node_dns(
            zone_id=zone_id,
            fqdn=fqdn,
            public_ip="192.0.2.1",
        )

    return {
        "instance_id": iid,
        "previous_state": ((row.get("PreviousState") or {}).get("Name") or "").strip() or None,
        "current_state": ((row.get("CurrentState") or {}).get("Name") or "").strip() or "stopping",
        "region": r,
        "fqdn": fqdn or None,
        "route53_zone_id": zone_id or None,
        "dns_change": dns_change,
        "dns_placeholder_ip": "192.0.2.1",
    }


def aws_wake(instance_id: str, *, fqdn: str = "") -> Dict[str, Any]:
    iid = str(instance_id or "").strip()
    fqdn = str(fqdn or "").strip()
    if not iid:
        raise ValueError("missing instance_id")

    r = region()
    ec2 = boto3.client("ec2", region_name=r)
    resp = ec2.start_instances(InstanceIds=[iid])

    items = list(resp.get("StartingInstances") or [])
    row = items[0] if items else {}

    inst_live = _wait_for_instance_network(ec2, iid)
    public_ip = str(inst_live.get("PublicIpAddress") or "").strip()
    private_ip = str(inst_live.get("PrivateIpAddress") or "").strip()
    state = str(
        ((inst_live.get("State") or {}).get("Name"))
        or ((row.get("CurrentState") or {}).get("Name"))
        or "running"
    ).strip()

    zone_id = _route53_zone_id()
    dns_change = None
    if zone_id and fqdn and public_ip:
        dns_change = _upsert_node_dns(
            zone_id=zone_id,
            fqdn=fqdn,
            public_ip=public_ip,
        )

    return {
        "instance_id": iid,
        "previous_state": ((row.get("PreviousState") or {}).get("Name") or "").strip() or None,
        "current_state": ((row.get("CurrentState") or {}).get("Name") or "").strip() or state,
        "state": state,
        "region": r,
        "fqdn": fqdn or None,
        "private_ip": private_ip,
        "public_ip": public_ip,
        "route53_zone_id": zone_id or None,
        "dns_change": dns_change,
    }


def aws_terminate(instance_id: str) -> Dict[str, Any]:
    iid = str(instance_id or "").strip()
    if not iid:
        raise ValueError("missing instance_id")

    r = region()
    ec2 = boto3.client("ec2", region_name=r)
    resp = ec2.terminate_instances(InstanceIds=[iid])

    items = list(resp.get("TerminatingInstances") or [])
    row = items[0] if items else {}
    return {
        "instance_id": iid,
        "previous_state": ((row.get("PreviousState") or {}).get("Name") or "").strip() or None,
        "current_state": ((row.get("CurrentState") or {}).get("Name") or "").strip() or "terminating",
        "region": r,
    }


def aws_list_nodes() -> Dict[str, Any]:
    r = region()
    ec2 = boto3.client("ec2", region_name=r)

    resp = ec2.describe_instances(
        Filters=[
            {"Name": "tag:taks.role", "Values": ["tak-node", "mr-node", "fire-dept-node", "company-node", "battalion-node"]},
        ]
    )

    instances: List[Dict[str, Any]] = []
    for res in resp.get("Reservations", []):
        for i in res.get("Instances", []):
            state = str((i.get("State") or {}).get("Name") or "").strip().lower()
            if state in {"terminated", "shutting-down"}:
                continue

            tags = {str(t.get("Key") or ""): str(t.get("Value") or "") for t in (i.get("Tags") or [])}
            instances.append(
                {
                    "instance_id": i.get("InstanceId"),
                    "state": state,
                    "private_ip": i.get("PrivateIpAddress"),
                    "public_ip": i.get("PublicIpAddress"),
                    "public_dns": i.get("PublicDnsName"),
                    "name": tags.get("Name", ""),
                    "role": tags.get("taks.role", ""),
                    "unit_path": tags.get("taks.unit_path", ""),
                    "region": r,
                    "availability_zone": ((i.get("Placement") or {}).get("AvailabilityZone") or ""),
                    "instance_type": i.get("InstanceType"),
                    "subnet_id": i.get("SubnetId"),
                    "vpc_id": i.get("VpcId"),
                    "image_id": i.get("ImageId"),
                    "launch_time": str(i.get("LaunchTime") or ""),
                    "iam_instance_profile_arn": ((i.get("IamInstanceProfile") or {}).get("Arn") or ""),
                    "security_groups": [
                        {
                            "group_id": str(g.get("GroupId") or ""),
                            "group_name": str(g.get("GroupName") or ""),
                        }
                        for g in (i.get("SecurityGroups") or [])
                    ],
                    "tags": tags,
                }
            )

    return {"provider": "aws", "region": r, "count": len(instances), "instances": instances}
