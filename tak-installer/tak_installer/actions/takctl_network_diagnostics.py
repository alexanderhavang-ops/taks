from pathlib import Path
import shutil
import subprocess
import tempfile

class _Action:
    ID='takctl-network-diagnostics'
    def inspect(self,ctx):return 0
    def apply(self,ctx):
        helper=Path('/usr/local/libexec/taks-network-capture');helper.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory() as temp:
            rule=Path(temp)/'sudoers'
            rule.write_text('Defaults:tak !requiretty\ntak ALL=(root) NOPASSWD: /usr/local/libexec/taks-network-capture *\n')
            subprocess.run(['visudo','-cf',str(rule)],check=True)
            shutil.copyfile(Path(ctx.repo_root)/'takctl/bin/taks-network-capture',helper)
            helper.chmod(0o755);shutil.chown(helper,'root','root')
            target=Path('/etc/sudoers.d/taks-network-capture');shutil.copyfile(rule,target);target.chmod(0o440);shutil.chown(target,'root','root')
        return 0
ACTION=_Action()
