"""The installer must record Failed when an action aborts."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tak_installer import engine


class InstallerFailureEvents(unittest.TestCase):
    def test_nonzero_return_records_failure(self):
        class Failed:
            ID = "mock-action"
            def apply(self, ctx):
                return 9
        with tempfile.TemporaryDirectory() as tmp, patch.object(engine, "discover_actions", return_value={"mock-action": Failed()}), patch.object(engine, "STATE_LOG", Path(tmp) / "state.log"):
            rc = engine.run_plan(engine.Context(repo_root=Path(tmp), dry_run=False, env={}), ["mock-action"])
            self.assertEqual(rc, 9)
            self.assertIn("tak-installer:mock-action", (Path(tmp) / "state.log").read_text())
            self.assertIn(",Failed", (Path(tmp) / "state.log").read_text())

    def test_exception_records_failure(self):
        class Raises:
            ID = "raise-action"
            def apply(self, ctx):
                raise RuntimeError("expected")
        with tempfile.TemporaryDirectory() as tmp, patch.object(engine, "discover_actions", return_value={"raise-action": Raises()}), patch.object(engine, "STATE_LOG", Path(tmp) / "state.log"):
            rc = engine.run_plan(engine.Context(repo_root=Path(tmp), dry_run=False, env={}), ["raise-action"])
            self.assertEqual(rc, 2)
            self.assertIn(",Failed", (Path(tmp) / "state.log").read_text())


if __name__ == "__main__":
    unittest.main()
