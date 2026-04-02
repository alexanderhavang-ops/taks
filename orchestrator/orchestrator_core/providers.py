from __future__ import annotations

from typing import Any, Dict

from orchestrator_core.config import load_orch_config
from orchestrator_core.core import (
    NodeRequest,
    aws_dry_run,
    aws_launch,
    aws_list_nodes,
    plan_node,
)


def cloud() -> str:
    return "aws"


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
    cfg = load_orch_config()
    if not cfg.aws.launch_enabled:
        raise RuntimeError("Launch disabled by config (aws.launch_enabled=false)")
    c = cloud()
    if c == "aws":
        return aws_launch(req)
    raise NotImplementedError(f"launch not implemented for cloud={c!r}")


def status_nodes() -> Dict[str, Any]:
    cfg = load_orch_config()
    c = cloud()

    if c == "aws":
        out = aws_list_nodes()
        if isinstance(out, dict):
            out["launch_enabled"] = cfg.aws.launch_enabled
            out["requirements"] = {
                "aws_key_name": bool(str(cfg.aws.ssh_key_name).strip()),
                "sg_id": bool(str(cfg.aws.default_security_group_id).strip()),
                "subnet_id": bool(str(cfg.aws.default_subnet_id).strip()),
                "image_id": bool(str(cfg.aws.default_ami).strip()),
            }
            out["hints"] = {
                "aws_key_name": "Set aws_default_key_name in runtime conf.d or pass aws_key_name in /nodes/launch request",
                "sg_id": "Set aws_default_security_group_id in runtime conf.d or pass aws_sg_id in /nodes/launch request",
                "subnet_id": "Set aws_default_subnet_id in runtime conf.d",
                "image_id": "Set aws_default_ami in runtime conf.d",
            }

        return out

    raise NotImplementedError(f"status not implemented for cloud={c!r}")
