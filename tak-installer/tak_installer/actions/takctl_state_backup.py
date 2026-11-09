from pathlib import Path
import shutil
import subprocess
import tempfile

HELPER = Path('/usr/local/libexec/taks-state-backup')
SUDOERS = Path('/etc/sudoers.d/taks-state-backup')
OPERATIONS = ('inventory', 'users', 'certs', 'cot_state', 'config', 'takctl_state', 'martine_state', 'documents', 'replay_state')
RULES = 'Defaults:tak !requiretty\n' + ''.join(f'tak ALL=(root) NOPASSWD: {HELPER} {op}\n' for op in OPERATIONS)


class _Action:
    ID = 'takctl-state-backup'

    def inspect(self, ctx):
        print(f'Root-owned backup helper: {HELPER.exists()}, sudo rule: {SUDOERS.exists()}')
        return 0

    def apply(self, ctx):
        source = ctx.repo_root / 'takctl/bin/taks-state-backup'
        with tempfile.TemporaryDirectory() as tmp:
            rules = Path(tmp) / 'sudoers'
            rules.write_text(RULES)
            subprocess.run(['visudo', '-cf', str(rules)], check=True)
            HELPER.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            shutil.copyfile(source, HELPER)
            HELPER.chmod(0o755)
            shutil.chown(HELPER, 'root', 'root')
            shutil.copyfile(rules, SUDOERS)
            SUDOERS.chmod(0o440)
            shutil.chown(SUDOERS, 'root', 'root')
        return 0


ACTION = _Action()
