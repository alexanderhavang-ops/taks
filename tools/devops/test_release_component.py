import importlib.util
from pathlib import Path
import sys
import types
import io
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch


class ReleaseBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        def register(catalog):
            for name in ("taks_operation_status", "taks_node_backup_start", "taks_backups_list",
                         "taks_backup_select_restore", "taks_bundle_prepare_start",
                         "taks_node_shutdown", "taks_node_launch_start"):
                def f(*a, _name=name):
                    self.calls.append((_name,a)); return {"ok":True}
                f.__name__=name
                catalog.tool()(f)
        self.submit=Mock(return_value={"ok":True})
        modules={"app":types.ModuleType("app"),
                 "app.orchestrator_component":types.SimpleNamespace(call=Mock(),launch_checked=Mock()),
                 "app.lifecycle_component":types.SimpleNamespace(submit=self.submit,register_lifecycle_tools=register,BUCKETS=("certs","users","config"))}
        self.guard=patch.dict(sys.modules,modules);self.guard.start()
        spec=importlib.util.spec_from_file_location("release_component",Path(__file__).with_name("release_component.py"))
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)

    def tearDown(self): self.guard.stop()

    def test_wrong_unit_or_missing_confirmation_never_mutates(self):
        for c in ("taks-release launch other confirm","taks-release launch taklabs",
                  "taks-release backup other confirm","taks-release shutdown other i-12345678 backup confirm",
                  "taks-release stage main","taks-release stage " + "a"*40 + "; id"):
            self.assertFalse(self.m.dispatch_release(c)["ok"])
        self.assertEqual(self.calls,[]);self.submit.assert_not_called()

    def test_backup_delegates_all_buckets(self):
        self.m.dispatch_release("taks-release backup taklabs.aws.tak-hv-sandbox.se confirm")
        self.assertEqual(self.calls,[("taks_node_backup_start",("taklabs.aws.tak-hv-sandbox.se",["certs","users","config"],True))])

    def test_shutdown_preserves_exact_instance_and_verified_backup_guard(self):
        self.m.dispatch_release("taks-release shutdown taklabs.aws.tak-hv-sandbox.se i-12345678 backup-1 confirm")
        self.assertEqual(self.calls,[("taks_node_shutdown",("taklabs.aws.tak-hv-sandbox.se","taklabs","i-12345678","backup-1",True))])

    def test_actual_bundle_members_and_activation_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive=Path(tmp)/"bundle.tar.gz"
            for enabled in (False,True):
                with tarfile.open(archive,"w:gz") as tar:
                    members={"taklabs/taks-source/"+p:b"source" for p in self.m.OVERLAYS}
                    members["taklabs/taks-source/simulation-source-commit"]=b"a"*40
                    members["taklabs/install/taks-bootstrap/config.d/simulation.conf"]=("simulation_enabled = "+str(enabled).lower()).encode()
                    for name,data in members.items():
                        info=tarfile.TarInfo(name);info.size=len(data);tar.addfile(info,io.BytesIO(data))
                with patch.object(self.m,"Path",return_value=archive):
                    result=self.m.verify_built_bundle()
                self.assertEqual(result["ok"],enabled)
                if enabled:self.assertEqual(result["checked_files"],10)


if __name__ == "__main__": unittest.main()
