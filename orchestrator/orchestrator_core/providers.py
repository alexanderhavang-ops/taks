from __future__ import annotations

import os
from typing import Any, Dict

from orchestrator_core.core import (
    NodeRequest,
    plan_node,
    aws_dry_run,
    aws_launch,
    aws_list_nodes,
)


def cloud() -> str:
    # Explicit selection; easy to extend later.
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
    # Safety gate: you must explicitly enable launch.
    if os.environ.get("TAKS_LAUNCH_ENABLED") != "1":
        raise RuntimeError("Launch disabled (set TAKS_LAUNCH_ENABLED=1 to enable)")
    c = cloud()
    if c == "aws":
        return aws_launch(req)
    raise NotImplementedError(f"launch not implemented for cloud={c!r}")


def status_nodes() -> Dict[str, Any]:
    c = cloud()
    if c == "aws":
        return aws_list_nodes()
    raise NotImplementedError(f"status not implemented for cloud={c!r}")

