import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('activity_install',Path(__file__).resolve().parents[1]/'tak-installer/tak_installer/actions/simulation_runtime.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class ActivityInstallationTests(unittest.TestCase):
 def test_disabled_simulation_still_installs_input_hooks(self):
  from types import SimpleNamespace
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'source';source.mkdir()
   with patch.object(m,'install_activity_hooks') as install:
    self.assertEqual(m.ACTION.apply(SimpleNamespace(repo_root=source)),0)
   install.assert_called_once_with(source)
 def test_restored_stale_agent_is_replaced_before_receivers_restart(self):
  files=['takctl/takctl/services/activity_evidence.py','martine/martine/activity_audit.py','martine/martine/agent/simple_agent.py','martine/martine/voice/mumble_ingest.py','martine/bin/martine-xmpp-inviter','takctl/takctl/web/mcp_domains/devops.py','takctl/takctl/web/mcp_domains/simulation_tools.py']
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'source';runtime=root/'runtime'
   for file in files:
    p=source/file;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('IDLE_AUDIT_HOOK_VERSION = 1\n')
   stale=runtime/files[2];stale.parent.mkdir(parents=True);stale.write_text('# restored old agent\n')
   def restarted(*args,**kwargs):self.assertIn('IDLE_AUDIT_HOOK_VERSION = 1',stale.read_text())
   with patch.object(m.shutil,'chown'),patch.object(m.subprocess,'run',side_effect=restarted) as restart:
    m.install_activity_hooks(source,runtime)
   self.assertIn('martine-xmpp-inviter.service',restart.call_args.args[0])
 def test_invalid_source_does_not_partially_replace_runtime(self):
  with tempfile.TemporaryDirectory() as tmp:
   with patch.object(m.subprocess,'run') as restart:
    with self.assertRaises(FileNotFoundError):m.install_activity_hooks(Path(tmp)/'missing',Path(tmp)/'runtime')
   restart.assert_not_called()
