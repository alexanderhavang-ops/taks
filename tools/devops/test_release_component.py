import importlib.util
from pathlib import Path
import sys
import types
import io
import json
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch


class ReleaseBoundaryTests(unittest.TestCase):
    def test_instance_tiers_match_simulation_memory_budgets(self):
        for capacity,shape in ((8,"t3.medium"),(256,"t3.medium"),(257,"t3.large"),(520,"t3.large"),(640,"t3.large"),(641,"t3.xlarge"),(1024,"t3.xlarge")):
            self.assertEqual(self.m.exercise_instance_type(capacity),shape)
        for capacity in (0,1025,True):
            with self.assertRaises(ValueError):self.m.exercise_instance_type(capacity)
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

    def test_web_logs_is_fixed_read_only_node_service(self):
        self.assertFalse(self.m.dispatch_release("taks-release web-logs other")["ok"])
        self.m.call.assert_not_called()
        self.m.dispatch_release("taks-release web-logs taklabs")
        args = self.m.call.call_args.args
        self.assertEqual(args[1], "/api/v2/nodes/taklabs.aws.tak-hv-sandbox.se/mcp/devops")
        self.assertEqual(args[2]["params"], {"name":"service_logs","arguments":{"service":"takctl-web.service","lines":80}})

    def test_identity_configuration_only_changes_next_boot_fragment(self):
        for command in ("taks-release identities other 520 confirm","taks-release identities taklabs 0 confirm", "taks-release identities taklabs 1025 confirm"):
            self.assertFalse(self.m.dispatch_release(command)["ok"])
        with tempfile.TemporaryDirectory() as tmp:
            fragment=Path(tmp)/"simulation.conf"
            with patch.object(self.m,"Path",return_value=fragment):
                result=self.m.dispatch_release("taks-release identities taklabs 520 confirm")
            self.assertTrue(result["ok"])
            self.assertFalse(result["running_node_changed"])
            self.assertIn("simulation_identity_capacity = 520",fragment.read_text())

    def test_node_resources_is_fixed_and_read_only(self):
        self.assertFalse(self.m.dispatch_release("taks-release resources other")["ok"])
        self.m.call.assert_not_called()
        self.m.dispatch_release("taks-release resources taklabs")
        args=self.m.call.call_args.args
        self.assertEqual(args[1],"/api/v2/nodes/taklabs.aws.tak-hv-sandbox.se/mcp/devops")
        self.assertEqual(args[2]["params"],{"name":"host_resources","arguments":{}})

    def test_checkpoint_preserves_selected_instance_and_avoids_tool_upload_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed=Path(tmp)/"state.json";seed.write_text(json.dumps({"orbat":{"instance_id":"selected"}}))
            state={"schema":1,"revision":42,"orbat":{"instance_id":"wrong"},"units":{"a":{"active":True,"entities":[{}]}}}
            def response():return {"result":{"content":[{"text":json.dumps({"ok":True,"state":state})}]}}
            with patch.object(self.m,"SEED_PATH",seed):
                self.m.call.return_value=response()
                with self.assertRaisesRegex(ValueError,"selected roster"):self.m.checkpoint_exercise()
                self.assertEqual(json.loads(seed.read_text())["orbat"]["instance_id"],"selected")
                state["orbat"]["instance_id"]="selected";self.m.call.return_value=response()
                result=self.m.checkpoint_exercise()
                self.assertEqual(result["active_personnel"],1)
                self.assertEqual(json.loads(seed.read_text())["revision"],42)

    def test_bundle_rejects_seed_beyond_its_certificate_capacity(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive=Path(tmp)/"bundle.tar.gz";seed=Path(tmp)/"seed.json"
            raw=json.dumps({"units":{"unit":{"entities":[{"identity_slot":519}]}}}).encode();seed.write_bytes(raw)
            for capacity in (8,520):
                with tarfile.open(archive,"w:gz") as tar:
                    members={"taklabs/taks-source/"+p:b"source" for p in self.m.OVERLAYS}
                    members["taklabs/taks-source/simulation-source-commit"]=b"a"*40
                    members["taklabs/install/taks-bootstrap/config.d/simulation.conf"]=f"simulation_enabled = true\nsimulation_identity_capacity = {capacity}".encode()
                    members["taklabs/misc/simulation-state.json"]=raw
                    for name,data in members.items():
                        info=tarfile.TarInfo(name);info.size=len(data);tar.addfile(info,io.BytesIO(data))
                with patch.object(self.m,"Path",return_value=archive),patch.object(self.m,"SEED_PATH",seed):
                    result=self.m.verify_built_bundle()
                self.assertEqual(result["ok"],capacity==520)
                if capacity==520:self.assertEqual(result["seed_personnel"],1)

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
                if enabled:self.assertEqual(result["checked_files"],len(self.m.OVERLAYS)+2)


if __name__ == "__main__": unittest.main()
