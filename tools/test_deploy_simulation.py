import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("deploy_simulation", Path(__file__).with_name("deploy-simulation-mvp.py"))
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class SelectedCapacityTest(unittest.TestCase):
    def test_bundle_overrides_restored_eight(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "taks-source"
            source.mkdir()
            conf = root / "install/taks-bootstrap/config.d/simulation.conf"
            conf.parent.mkdir(parents=True)
            conf.write_text("simulation_enabled = true\nsimulation_identity_capacity = 520\n")
            self.assertEqual(deploy.selected_identity_capacity(source, 8), (520, "bundle"))
            for value in ("0", "1025", "nope"):
                conf.write_text("simulation_identity_capacity = " + value)
                with self.assertRaises(ValueError):
                    deploy.selected_identity_capacity(source, 8)
            conf.write_text("simulation_enabled=true\n")
            with self.assertRaises(ValueError):
                deploy.selected_identity_capacity(source, 8)

    def test_standalone_fallbacks(self):
        with tempfile.TemporaryDirectory() as folder:
            conf = Path(folder) / "simulation.conf"
            self.assertEqual(deploy.selected_identity_capacity(None, 16, conf), (16, "argument"))
            self.assertEqual(deploy.selected_identity_capacity(None, None, conf), (8, "runtime/default"))
            conf.write_text("simulation_identity_capacity=32\n")
            self.assertEqual(deploy.selected_identity_capacity(None, None, conf), (32, "runtime/default"))


if __name__ == "__main__":
    unittest.main()
