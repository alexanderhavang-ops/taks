from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

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
    tpl = jinja_env().get_template("tak-node.cloud-init.yml.j2")
    return tpl.render(battalion=battalion, fqdn=fqdn, hostname=hostname)


def validate_cloud_init(text: str) -> None:
    if not text.lstrip().startswith("#cloud-config"):
        raise ValueError("cloud-init must start with #cloud-config")
    yaml.safe_load(text)  # raises on invalid yaml


def resolve_ubuntu_2204_ami(*, region_name: str) -> str:
    ssm = boto3.client("ssm", region_name=region_name)
    p = "/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
    r = ssm.get_parameter(Name=p)
    return r["Parameter"]["Value"]


def resolve_default_public_subnet(*, region_name: str) -> Dict[str, str]:
    ec2 = boto3.client("ec2", region_name=region_name)
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"]
    if not vpcs:
        raise RuntimeError("no default VPC found (we will add explicit VPC support later)")
    vpc_id = vpcs[0]["VpcId"]
    subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])["Subnets"]
    pub = [s for s in subnets if s.get("MapPublicIpOnLaunch")]
    if not pub:
        raise RuntimeError("no public subnet found in default VPC (MapPublicIpOnLaunch=true)")
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
    ci = render_cloud_init(battalion=req.battalion, fqdn=req.fqdn, hostname=req.hostname)
    validate_cloud_init(ci)
    return {
        "region": r,
        "ami": ami,
        "vpc_id": net["vpc_id"],
        "subnet_id": net["subnet_id"],
        "instance_type": req.instance_type,
        "tags": {"Name": req.name, "taks.role": "tak-node", "taks.battalion": req.battalion},
        "cloud_init": ci,
    }


def aws_dry_run(req: NodeRequest) -> Dict[str, Any]:
    p = plan_node(req)
    ec2 = boto3.client("ec2", region_name=p["region"])
    user_data_b64 = base64.b64encode(p["cloud_init"].encode("utf-8")).decode("ascii")
    try:
        ec2.run_instances(
            ImageId=p["ami"],
            InstanceType=p["instance_type"],
            MinCount=1,
            MaxCount=1,
            SubnetId=p["subnet_id"],
            UserData=user_data_b64,
            TagSpecifications=[{
                "ResourceType": "instance",
                "Tags": [{"Key": k, "Value": v} for k, v in p["tags"].items()],
            }],
            DryRun=True,
        )
        # Would be weird to succeed with DryRun=True; AWS usually throws DryRunOperation
        return {"dry_run_ok": True, "note": "unexpected success response", "plan": {k: p[k] for k in p if k != "cloud_init"}}
    except ec2.exceptions.ClientError as e:
        if "DryRunOperation" in str(e):
            return {"dry_run_ok": True, "plan": {k: p[k] for k in p if k != "cloud_init"}}
        raise
