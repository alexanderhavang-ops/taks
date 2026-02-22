from __future__ import annotations

"""
takctl.render

Contract-only render schemas used by CLI + Web.
Backend returns RenderPlan JSON; frontends render it.
"""

from takctl.render.plan import RENDERPLAN_VERSION, RenderPlanError, validate_renderplan

__all__ = ["RENDERPLAN_VERSION", "RenderPlanError", "validate_renderplan"]
