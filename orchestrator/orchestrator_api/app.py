# Stable import path / entrypoint for uvicorn/systemd.
#
# NOTE: systemd runs uvicorn with:
#   --app-dir /opt/tak-orch/orchestrator  orchestrator_api.app:app
# so imports must be relative to that app-dir (no top-level "orchestrator" pkg).
from orchestrator_api.main import app  # noqa: F401
