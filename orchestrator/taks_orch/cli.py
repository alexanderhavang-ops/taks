from __future__ import annotations

import argparse
import base64
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import boto3
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined


_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATES = _REPO_ROOT / "orchestrator" / "templates"


def _region() -> str:
    # Prefer env; fallback to IMDS/SDK default resolution.
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "eu-north-1"


def _jinja() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )


def render_cloud_init(*, battalion: str, fqdn: str, hostname: str) -> str:
    tpl = _jinja().get_template("tak-node.cloud-init.yml.j2")
    return tpl.render(battalion=battalion, fqdn=fqdn, hostname=hostname)


def validate_cloud_init(text: str) -> None:
    # Basic: must start with #cloud-config and be valid YAML
    if not text.lstrip().startswith("#cloud-config"):
        raise SystemExit("cloud-init must start with #cloud-config")
    try:
        yaml.safe_load(text)
    except Exception as e:
        raise SystemExit(f"cloud-init yaml parse failed: {e}") from e


@dataclass
class SpawnSpec:
    name: str
    battalion: str
    fqdn: str
    hostname: str
    instance_type: str = "t3.micro"


def _resolve_ubuntu_2204_ami(ssm, region: str) -> str:
    p = "/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
    r = ssm.get_parameter(Name=p)
    return r["Parameter"]["Value"]


def spawn_node(spec: SpawnSpec, *, dry_run: bool) -> Dict[str, Any]:
    region = _region()
    ec2 = boto3.client("ec2", region_name=region)
    ssm = boto3.client("ssm", region_name=region)

    ami = _resolve_ubuntu_2204_ami(ssm, region)

    # Default VPC + a public subnet
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"]
    if not vpcs:
        raise SystemExit("no default VPC found (set VPC explicitly later)")
    vpc_id = vpcs[0]["VpcId"]

    subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])["Subnets"]
    pub = [s for s in subnets if s.get("MapPublicIpOnLaunch")]
    if not pub:
        raise SystemExit("no public subnet found in default VPC (MapPublicIpOnLaunch=true)")
    subnet_id = sorted(pub, key=lambda s: s["SubnetId"])[0]["SubnetId"]

    user_data = render_cloud_init(battalion=spec.battalion, fqdn=spec.fqdn, hostname=spec.hostname)
    validate_cloud_init(user_data)

    # NOTE: we intentionally do NOT create SG/keypair yet in step 1.
    # For dry-run: use DryRun=True to verify permissions and request validity.
    req = dict(
        ImageId=ami,
        InstanceType=spec.instance_type,
        MinCount=1,
        MaxCount=1,
        SubnetId=subnet_id,
        UserData=base64.b64encode(user_data.encode("utf-8")).decode("ascii"),
        TagSpecifications=[{
            "ResourceType": "instance",
            "Tags": [
                {"Key": "Name", "Value": spec.name},
                {"Key": "taks.role", "Value": "tak-node"},
                {"Key": "taks.battalion", "Value": spec.battalion},
            ],
        }],
        DryRun=dry_run,
    )

    # If dry-run, AWS will raise DryRunOperation if it *would* succeed.
    try:
        resp = ec2.run_instances(**req)
        return {"ran": True, "response": resp}
    except ec2.exceptions.ClientError as e:
        msg = str(e)
        if "DryRunOperation" in msg:
            return {"ran": False, "dry_run_ok": True, "region": region, "subnet_id": subnet_id, "ami": ami}
        raise


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="taks-orch")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render-cloud-init")
    r.add_argument("--battalion", required=True)
    r.add_argument("--fqdn", required=True)
    r.add_argument("--hostname", required=True)

    v = sub.add_parser("validate-cloud-init")
    v.add_argument("--file", required=True)

    s = sub.add_parser("spawn")
    s.add_argument("--battalion", required=True)
    s.add_argument("--fqdn", required=True)
    s.add_argument("--hostname", required=True)
    s.add_argument("--name", required=True)
    s.add_argument("--instance-type", default="t3.micro")
    s.add_argument("--dry-run", action="store_true")

    args = ap.parse_args(argv)

    if args.cmd == "render-cloud-init":
        txt = render_cloud_init(battalion=args.battalion, fqdn=args.fqdn, hostname=args.hostname)
        print(txt, end="")
        return 0

    if args.cmd == "validate-cloud-init":
        txt = Path(args.file).read_text(encoding="utf-8")
        validate_cloud_init(txt)
        print("OK")
        return 0

    if args.cmd == "spawn":
        spec = SpawnSpec(
            name=args.name,
            battalion=args.battalion,
            fqdn=args.fqdn,
            hostname=args.hostname,
            instance_type=args.instance_type,
        )
        out = spawn_node(spec, dry_run=bool(args.dry_run))
        print(yaml.safe_dump(out, sort_keys=False), end="")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
