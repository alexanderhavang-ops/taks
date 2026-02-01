from __future__ import annotations
from dataclasses import dataclass
from .sections import FileSection

@dataclass(frozen=True)
class Profile:
    name: str
    intent: str
    sections: list[FileSection]

def get_profile(name: str) -> Profile:
    n = (name or "").strip().lower()
    if n == "orchestrator":
        return Profile(
            name="orchestrator",
            intent=(
                "Paste this into a fresh ChatGPT chat to continue TAK orchestrator work with full context. "
                "Includes repo status, recent commits, key orchestrator installer code/config, and related notes."
            ),
            sections=[
                FileSection("Architecture / Notes", "orchestrator-installer/docs/README.md", optional=True),
                FileSection("Architecture / Notes", "tak-installer/offline/README.md", optional=True),

                FileSection("Orchestrator installer entrypoint", "orchestrator-installer/scripts/orch-install", optional=False),
                FileSection("Orchestrator installer core", "orchestrator-installer/lib/00_core.sh", optional=True),
                FileSection("Orchestrator installer packages", "orchestrator-installer/lib/10_packages.sh", optional=True),
                FileSection("Orchestrator app install", "orchestrator-installer/lib/20_orch_app.sh", optional=True),
                FileSection("Orchestrator nginx+LE", "orchestrator-installer/lib/30_nginx_le.sh", optional=True),

                FileSection("Orchestrator cloud-init", "orchestrator-installer/cloud-init/orchestrator.yaml", optional=True),
                FileSection("Orchestrator systemd unit", "orchestrator-installer/systemd/tak-orch.service", optional=True),

                FileSection("TAK node installer entrypoint", "tak-installer/scripts/tak-install", optional=True),
                FileSection("TAK node libs", "tak-installer/lib/00_core.sh", optional=True),
                FileSection("TAK node libs", "tak-installer/lib/10_install_mechanics.sh", optional=True),
                FileSection("TAK node libs", "tak-installer/lib/20_cert_layout.sh", optional=True),
                FileSection("TAK node libs", "tak-installer/lib/30_nginx.sh", optional=True),
                FileSection("TAK node libs", "tak-installer/lib/40_certs.sh", optional=True),
                FileSection("TAK node call-home", "tak-installer/lib/90_call_home.sh", optional=True),

                FileSection("TAK node cloud-init", "tak-installer/cloud-init/taknode.yaml", optional=True),
                FileSection("Offline manifest", "tak-installer/offline/apt-packages.txt", optional=True),
                FileSection("Offline manifest", "tak-installer/offline/manifests/bundle.manifest.txt", optional=True),

                FileSection("Chatpack readme", "chatpack/README.md", optional=True),
            ],
        )

    # fallback minimal profile
    return Profile(
        name=n or "default",
        intent="General chatpack snapshot.",
        sections=[
            FileSection("Chatpack readme", "chatpack/README.md", optional=True),
        ],
    )
