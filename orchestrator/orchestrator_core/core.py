from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def render_cloud_init(*, battalion: str, fqdn: str, hostname: str) -> str:
    """
    Render cloud-init for a node.

    Template-driven so WebUI / CLI / API stay consistent.
    Injects headless orchestrator credentials so the node can call back home.
    """
    orch_api_url = (
        os.environ.get("TAKS_ORCH_API_URL")
        or os.environ.get("ORCH_API_URL")
        or "https://master.tak-hv-sandbox.se"
    )

    orch_api_user = (
        os.environ.get("TAKS_API_USER")
        or os.environ.get("ORCH_API_USER")
        or "orchestrator"
    ).strip()

    orch_api_password = (
        os.environ.get("TAKS_API_PASSWORD")
        or os.environ.get("ORCH_API_PASSWORD")
        or os.environ.get("TAKS_UI_PASSWORD")
        or "changeme"
    )

    tpl = jinja_env().get_template("tak-node.cloud-init.yml.j2")
    return tpl.render(
        battalion=battalion,
        fqdn=fqdn,
        hostname=hostname,
        orch_api_url=orch_api_url,
        orch_api_user=orch_api_user,
        orch_api_password=orch_api_password,
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
    battalion: str
    fqdn: str
    hostname: str
    name: str
    instance_type: str = "t3.micro"


def plan_node(req: NodeRequest) -> Dict[str, Any]:
    r = region()
    ami = resolve_ubuntu_2204_ami(region_name=r)
    net = resolve_default_public_subnet(region_name=r)
    ci = render_cloud_init(
        battalion=req.battalion,
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
            "taks.role": "tak-node",
            "taks.battalion": req.battalion,
        },
        "cloud_init": ci,
    }

