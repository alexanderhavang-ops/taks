# Action modules live in this package.
# Each actionable module exports a top-level ACTION object with an ID.

# takctl-llm-kick (one-shot tactical refresh helper)
from . import takctl_llm_kick  # noqa: F401
from . import systemd_takctl_llm_refresh_tactical  # noqa: F401

