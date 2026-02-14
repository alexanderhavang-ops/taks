from __future__ import annotations

import os
from typing import Any, Dict

from orchestrator_core.core import (
    NodeRequest,
    aws_dry_run,
    aws_launch,
    aws_list_nodes,
    plan_node,
)


def cloud() -> str:
    return (os.environ.get("TAKS_CLOUD") or "aws").strip().lower()


def preview_node(req: NodeRequest) -> Dict[str, Any]:
    c = cloud()
    if c == "aws":
        return plan_node(req)
    raise NotImplementedError(f"preview not implemented for cloud={c!r}")


def dry_run_node(req: NodeRequest) -> Dict[str, Any]:
    c = cloud()
    if c == "aws":
        return aws_dry_run(req)
    raise NotImplementedError(f"dry_run not implemented for cloud={c!r}")


def launch_node(req: NodeRequest) -> Dict[str, Any]:
    if os.environ.get("TAKS_LAUNCH_ENABLED") != "1":
        raise RuntimeError("Launch disabled (set TAKS_LAUNCH_ENABLED=1 to enable)")
    c = cloud()
    if c == "aws":
        return aws_launch(req)
    raise NotImplementedError(f"launch not implemented for cloud={c!r}")


def status_nodes() -> Dict[str, Any]:
    c = cloud()
    launch_enabled = (os.environ.get("TAKS_LAUNCH_ENABLED") == "1")

    if c == "aws":
        out = aws_list_nodes()
        if isinstance(out, dict):
            out["launch_enabled"] = launch_enabled

            # Operator-visible requirements for /nodes/launch.
            # We do NOT attempt AWS discovery (instance role may not have Describe*).
            # Values can be provided via env and/or request fields (where supported).
            reqs = {
                "aws_key_name": bool((os.environ.get("TAKS_AWS_KEY_NAME") or "").strip()),
                "sg_id": bool((os.environ.get("TAKS_AWS_SG_ID") or "").strip()),
                "subnet_id": bool((os.environ.get("TAKS_SUBNET_ID") or "").strip()),
                "image_id": bool((os.environ.get("TAKS_IMAGE_ID") or "").strip()),
            }
            out["requirements"] = reqs
            out["hints"] = {
                "aws_key_name": "Set env TAKS_AWS_KEY_NAME (EC2 keypair name) or pass aws_key_name in /nodes/launch request",
                "sg_id": "Set env TAKS_AWS_SG_ID to a security group *ID* (sg-...) in the same VPC as the subnet",
                "subnet_id": "Set env TAKS_SUBNET_ID (subnet-...)",
                "image_id": "Set env TAKS_IMAGE_ID (ami-...)",
            }

        return out

    raise NotImplementedError(f"status not implemented for cloud={c!r}")

