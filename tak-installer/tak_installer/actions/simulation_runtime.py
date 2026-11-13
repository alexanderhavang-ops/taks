"""Install the explicit exercise daemon as part of the cattle node build."""
from pathlib import Path
import subprocess
import sys


class SimulationRuntime:
    ID = "simulation-runtime"

    def inspect(self, ctx):
        print("simulation-runtime: explicit execution daemon, enabled per unit bootstrap")
        return 0

    def apply(self, ctx):
        # The unit bootstrap is authoritative even when older runtime config
        # has been restored from the previous cow.
        conf = Path("/etc/taks-bootstrap.d/config.d/simulation.conf")
        values = {}
        if conf.exists():
            for line in conf.read_text().splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    values[k.strip()] = v.strip()
        if values.get("simulation_enabled", "false").lower() != "true":
            print("simulation-runtime: disabled for this unit")
            return 0
        source = Path(ctx.repo_root)
        commit = (source / "simulation-source-commit").read_text().strip()
        subprocess.run([sys.executable, str(source / "tools/deploy-simulation-mvp.py"),
                        "--commit", commit, "--source-root", str(source),
                        "--identities", values.get("simulation_identity_capacity","8")], check=True)
        return 0


ACTION = SimulationRuntime()
