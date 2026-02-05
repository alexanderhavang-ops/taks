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
    tpl = jinja_env().get_template("tak-node.cloud-init.yml.j2")
    return tpl.render(battalion=battalion, fqdn=fqdn, hostname=hostname)


def validate_cloud_init(text: str) -> None:
    if not text.lstrip().startswith("#cloud-config"):
        raise ValueError("cloud-init must start with #cloud-config")
    yaml.safe_load(text)  # raises on invalid yaml


def resolve_ubuntu_2204_ami(*, region_name: str) -> str:
    # Cloud-agnostic override: let callers pin an image id explicitly.
    pinned = os.environ.get("TAKS_IMAGE_ID")
    if pinned:
        return pinned

    # AWS default: prefer Canonical's public SSM parameter...
    ssm = boto3.client("ssm", region_name=region_name)
    param = "/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
    try:
        r = ssm.get_parameter(Name=param)
        return r["Parameter"]["Value"]
    except Exception as e:
        # ...but some roles do not allow ssm:GetParameter. Fall back to DescribeImages.
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
        raise RuntimeError("No Ubuntu 22.04 images found via DescribeImages (need TAKS_IMAGE_ID or broaden filters)")

    imgs.sort(key=lambda im: im.get("CreationDate", ""), reverse=True)
    return imgs[0]["ImageId"]


def resolve_default_public_subnet(*, region_name: str) -> Dict[str, str]:
    pinned_subnet = os.environ.get("TAKS_SUBNET_ID")
    if pinned_subnet:
        # When IAM is locked down, skip DescribeVpcs/DescribeSubnets.
        # vpc_id is informational only in our plan.
        return {"vpc_id": "pinned", "subnet_id": pinned_subnet}

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
    user_data = p["cloud_init"]  # boto3 expects plain text here
    try:
        ec2.run_instances(
            ImageId=p["ami"],
            InstanceType=p["instance_type"],
            MinCount=1,
            MaxCount=1,
            SubnetId=p["subnet_id"],
            UserData=user_data,
            TagSpecifications=[
                {
                    "ResourceType": "instance",
                    "Tags": [{"Key": k, "Value": v} for k, v in p["tags"].items()],
                }
            ],
            DryRun=True,
        )
        return {
            "dry_run_ok": True,
            "note": "unexpected success response",
            "plan": {k: p[k] for k in p if k != "cloud_init"},
        }
    except ec2.exceptions.ClientError as e:
        if "DryRunOperation" in str(e):
            return {"dry_run_ok": True, "plan": {k: p[k] for k in p if k != "cloud_init"}}
        raise


def aws_launch(req: NodeRequest) -> Dict[str, Any]:
    """
    AWS launch implementation.

    Safety: requires explicit KeyName + SG id so we don't create unreachable instances.
    """
    p = plan_node(req)

    key_name = os.environ.get("TAKS_AWS_KEY_NAME")
    sg_id = os.environ.get("TAKS_AWS_SG_ID")

    if not key_name:
        raise RuntimeError("Missing env TAKS_AWS_KEY_NAME (EC2 keypair name)")
    if not sg_id:
        raise RuntimeError("Missing env TAKS_AWS_SG_ID (Security Group id, e.g. sg-...)")

    ec2 = boto3.client("ec2", region_name=p["region"])
    user_data = p["cloud_init"]

    r = ec2.run_instances(
        ImageId=p["ami"],
        InstanceType=p["instance_type"],
        MinCount=1,
        MaxCount=1,
        SubnetId=p["subnet_id"],
        SecurityGroupIds=[sg_id],
        KeyName=key_name,
        UserData=user_data,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [{"Key": k, "Value": v} for k, v in p["tags"].items()],
            }
        ],
        DryRun=False,
    )

    inst = r["Instances"][0]
    return {
        "launched": True,
        "provider": "aws",
        "instance_id": inst.get("InstanceId"),
        "state": (inst.get("State") or {}).get("Name"),
        "plan": {k: p[k] for k in p if k != "cloud_init"},
        "note": "Instance may take time to get PublicIpAddress; status endpoint will show when ready.",
    }


def _tag_map(tags: Optional[List[Dict[str, str]]]) -> Dict[str, str]:
    if not tags:
        return {}
    out: Dict[str, str] = {}
    for t in tags:
        k = t.get("Key")
        v = t.get("Value")
        if k is not None and v is not None:
            out[k] = v
    return out


def aws_list_nodes() -> Dict[str, Any]:
    """
    Inventory + health for all running TAKS-managed TAK nodes.

    We intentionally keep this shallow:
    - EC2 instance state + IPs + launch time
    - AWS status checks (system/instance)
    """
    r = region()
    ec2 = boto3.client("ec2", region_name=r)

    resp = ec2.describe_instances(
        Filters=[
            {"Name": "tag:taks.role", "Values": ["tak-node"]},
            {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]},
        ]
    )

    instances: List[Dict[str, Any]] = []
    ids: List[str] = []

    for res in resp.get("Reservations", []):
        for inst in res.get("Instances", []):
            iid = inst.get("InstanceId")
            if iid:
                ids.append(iid)
            tags = _tag_map(inst.get("Tags"))
            instances.append(
                {
                    "instance_id": iid,
                    "state": (inst.get("State") or {}).get("Name"),
                    "public_ip": inst.get("PublicIpAddress"),
                    "private_ip": inst.get("PrivateIpAddress"),
                    "launch_time": (inst.get("LaunchTime").isoformat() if inst.get("LaunchTime") else None),
                    "az": (inst.get("Placement") or {}).get("AvailabilityZone"),
                    "instance_type": inst.get("InstanceType"),
                    "name": tags.get("Name"),
                    "taks_battalion": tags.get("taks.battalion"),
                    "tags": tags,
                }
            )

    status_by_id: Dict[str, Any] = {}
    if ids:
        st = ec2.describe_instance_status(InstanceIds=ids, IncludeAllInstances=True)
        for s in st.get("InstanceStatuses", []):
            iid = s.get("InstanceId")
            status_by_id[iid] = {
                "system_status": ((s.get("SystemStatus") or {}).get("Status")),
                "instance_status": ((s.get("InstanceStatus") or {}).get("Status")),
            }

    for i in instances:
        iid = i.get("instance_id")
        i["aws_checks"] = status_by_id.get(iid, {"system_status": None, "instance_status": None})

    instances.sort(key=lambda x: (x.get("taks_battalion") or "", x.get("name") or "", x.get("instance_id") or ""))

    return {"provider": "aws", "region": r, "count": len(instances), "instances": instances}

