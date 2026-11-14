"""Install the explicit exercise daemon as part of the cattle node build."""
from pathlib import Path
import subprocess
import sys
import os
import shutil


def install_activity_hooks(source, runtime=Path("/opt/tak/tools")):
    files={
        "takctl/takctl/services/activity_evidence.py":"takctl/takctl/services/activity_evidence.py",
        "martine/martine/activity_audit.py":"martine/martine/activity_audit.py",
        "martine/martine/agent/simple_agent.py":"martine/martine/agent/simple_agent.py",
        "martine/martine/voice/mumble_ingest.py":"martine/martine/voice/mumble_ingest.py",
        "martine/bin/martine-xmpp-inviter":"martine/bin/martine-xmpp-inviter",
        "takctl/takctl/web/mcp_domains/devops.py":"takctl/takctl/web/mcp_domains/devops.py",
        "takctl/takctl/web/mcp_domains/simulation_tools.py":"takctl/takctl/web/mcp_domains/simulation_tools.py",
    }
    contents={path:(source/path).read_bytes() for path in files}
    for path,data in contents.items():compile(data,path,"exec")
    for path,data in contents.items():
        dst=runtime/files[path];dst.parent.mkdir(parents=True,exist_ok=True)
        temporary=dst.with_suffix(dst.suffix+".activity-tmp")
        temporary.write_bytes(data);temporary.chmod(0o750 if "/bin/" in path else 0o640)
        shutil.chown(temporary,user="tak",group="tak");os.replace(temporary,dst)
    subprocess.run(["systemctl","try-restart","takctl-web.service","martine-cot.service",
                    "martine-xmpp-inviter.service","martine-voice-transcribe.service"],check=True)


class SimulationRuntime:
    ID = "simulation-runtime"

    def inspect(self, ctx):
        print("simulation-runtime: explicit execution daemon, enabled per unit bootstrap")
        return 0

    def apply(self, ctx):
        # The unit bootstrap is authoritative even when older runtime config
        # has been restored from the previous cow.
        source = Path(ctx.repo_root)
        install_activity_hooks(source)
        bundled = source.parent / "install/taks-bootstrap/config.d/simulation.conf"
        conf = bundled if bundled.is_file() else Path("/etc/taks-bootstrap.d/config.d/simulation.conf")
        values = {}
        if conf.exists():
            for line in conf.read_text().splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    values[k.strip()] = v.strip()
        if values.get("simulation_enabled", "false").lower() != "true":
            print("simulation-runtime: disabled for this unit")
            return 0
        commit = (source / "simulation-source-commit").read_text().strip()
        subprocess.run([sys.executable, str(source / "tools/deploy-simulation-mvp.py"),
                        "--commit", commit, "--source-root", str(source),
                        "--identities", values.get("simulation_identity_capacity","8")], check=True)
        return 0


ACTION = SimulationRuntime()
