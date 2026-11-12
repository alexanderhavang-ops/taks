import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.context, self.run, self.remote = Mock(), Mock(), Mock()
        modules = {"app": types.ModuleType("app"),
                   "app.cert_ops_component": types.SimpleNamespace(run=self.run, remote=self.remote),
                   "app.route53_component": types.SimpleNamespace(_node_context=self.context, _ec2_ip=Mock())}
        self.patch = patch.dict(sys.modules, modules)
        self.patch.start()
        spec = importlib.util.spec_from_file_location("simulation_ops", Path(__file__).with_name("simulation_ops.py"))
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def tearDown(self):
        self.patch.stop()

    def test_invalid_commands_have_no_remote_side_effect(self):
        for text in ("id", "taks-mvp deploy node main", "taks-mvp deploy node;id " + "a"*40,
                     "taks-mvp inspect node extra", "taks-mvp poll node nope"):
            self.assertFalse(self.module.dispatch_mvp(text)["ok"])
        self.context.assert_not_called()
        self.run.assert_not_called()
        self.remote.assert_not_called()

    def test_deploy_uses_fixed_repository_and_pinned_sha(self):
        self.context.return_value = ({"unit_path":"lab"},"zone","eu-north-1","lab.example","i-12345678")
        self.run.return_value = {"ok": True, "stdout":"11111111-1111-1111-1111-111111111111"}
        result = self.module.dispatch_mvp("taks-mvp deploy lab.example " + "a"*40)
        self.assertEqual(result["status"], "submitted")
        argv = self.run.call_args.args[0]
        self.assertIn("send-command",argv)
        import json
        params = json.loads(argv[argv.index("--parameters")+1])
        self.assertIn("alexanderhavang-ops/taks/" + "a"*40, params["commands"][0])
        self.assertEqual(params["executionTimeout"],["300"])


if __name__ == "__main__": unittest.main()
