from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import boto3
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = REPO_ROOT / "orchestrator" / "templates"


def region() -> str:
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "eu-north-1"


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
    orch_api_url = (
        os.environ.get("TAKS_ORCH_API_URL")
        or os.environ.get("ORCH_API_URL")
        or "https://master.tak-hv-sandbox.se"
    )

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


def resolve_ubuntu_2204_ami(*, region_name: str) -> str:
    pinned = os.environ.get("TAKS_IMAGE_ID")
    if pinned:
        return pinned

    ssm = boto3.client("ssm", region_name=region_name)
    param = "/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp3/ami-id"

    try:
        r = ssm.get_parameter(Name=param)
        return r["Parameter"]["Value"]
    except Exception as e:
        msg = str(e)
        if "AccessDenied" not in msg and "AccessDeniedException" not in msg:
            raise

    ec2 = boto3.client("ec2", region_name=region_name)

    canonical_owner = "099720109477"
    name_glob = "ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"

    imgs = ec2.describe_images(
        Owners=[canonical_owner],
        Filters=[
            {"Name": "name", "Values": [name_glob]},
            {"Name": "state", "Values": ["available"]},
            {"Name": "architecture", "Values": ["x86_64"]},
            {"Name": "virtualization-type", "Values": ["hvm"]},
        ],
    )["Images"]

    if not imgs:
        raise RuntimeError("No Ubuntu 22.04 images found")

    imgs.sort(key=lambda im: im.get("CreationDate", ""), reverse=True)
    return imgs[0]["ImageId"]


def resolve_default_public_subnet(*, region_name: str) -> Dict[str, str]:
    pinned_subnet = os.environ.get("TAKS_SUBNET_ID")
    if pinned_subnet:
        return {"vpc_id": "pinned", "subnet_id": pinned_subnet}

    ec2 = boto3.client("ec2", region_name=region_name)
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"]
    if not vpcs:
        raise RuntimeError("no default VPC found")

    vpc_id = vpcs[0]["VpcId"]
    subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])["Subnets"]
    pub = [s for s in subnets if s.get("MapPublicIpOnLaunch")]
    if not pub:
        raise RuntimeError("no public subnet found")

    subnet_id = sorted(pub, key=lambda s: s["SubnetId"])[0]["SubnetId"]
    return {"vpc_id": vpc_id, "subnet_id": subnet_id}


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
    ami = resolve_ubuntu_2204_ami(region_name=r)
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


def aws_launch(req: NodeRequest) -> Dict[str, Any]:
    r = region()
    plan = plan_node(req)

    sg_id = (req.aws_sg_id or os.environ.get("TAKS_AWS_SG_ID") or "").strip()
    key_name = (req.aws_key_name or os.environ.get("TAKS_AWS_KEY_NAME") or "").strip()

    if not sg_id:
        raise RuntimeError("Missing security group id (set TAKS_AWS_SG_ID or pass aws_sg_id)")
    if not key_name:
        raise RuntimeError("Missing EC2 keypair name (set TAKS_AWS_KEY_NAME or pass aws_key_name)")

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
        "TagSpecifications": [
            {
                "ResourceType": "instance",
                "Tags": [{"Key": k, "Value": str(v)} for k, v in plan["tags"].items()],
            }
        ],
    }

    resp = ec2.run_instances(**kwargs)
    inst = resp["Instances"][0]

    return {
        "instance_id": inst["InstanceId"],
        "state": inst["State"]["Name"],
        "region": r,
        "subnet_id": plan["subnet_id"],
        "sg_id": sg_id,
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
            tags = {str(t.get("Key") or ""): str(t.get("Value") or "") for t in (i.get("Tags") or [])}
            instances.append(
                {
                    "instance_id": i.get("InstanceId"),
                    "state": (i.get("State") or {}).get("Name"),
                    "private_ip": i.get("PrivateIpAddress"),
                    "public_ip": i.get("PublicIpAddress"),
                    "public_dns": i.get("PublicDnsName"),
                    "name": tags.get("Name", ""),
                    "role": tags.get("taks.role", ""),
                    "unit_path": tags.get("taks.unit_path", ""),
                }
            )

    return {"provider": "aws", "region": r, "count": len(instances), "instances": instances}
