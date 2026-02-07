from __future__ import annotations

"""
takctl.services.llm

Public surface for the LLM subsystem.

Rules:
- This package is the only owner of the "llm" name under takctl.services.
- Keep this file as a thin re-export layer to avoid circular imports.
"""

from takctl.services.llm.client import LLMClient

# Temporary compat: legacy status function still lives here until fully migrated.
from takctl.services.llm._legacy_llm_module import llm_status

__all__ = [
    "LLMClient",
    "llm_status",
]
