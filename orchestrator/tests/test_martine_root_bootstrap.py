"""Offline tests for root-level inherited Martine secrets."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from orchestrator_core import unit_bootstrap as ub


def _load_importer():
    script = Path(__file__).resolve().parents[1] / "bin" / "import-martine-api-key"
    spec = importlib.util.spec_from_file_location("martine_key_importer", script)
    # The script has no .py suffix, so import via SourceFileLoader explicitly.
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader("martine_key_importer", str(script))
    spec = importlib.util.spec_from_loader("martine_key_importer", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class RootBootstrapTests(unittest.TestCase):
    def test_global_secret_inherited_across_unrelated_unit_trees(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with patch.object(ub, "_state_dir", return_value=root), patch.object(
                ub, "inheritance_chain_root_to_leaf",
                side_effect=lambda unit: [unit],
            ):
                base = ub.global_bootstrap_dir(secret=True)
                base.mkdir(parents=True)
                (base / "martine.conf").write_text("martine_openai_api_key = sk-test-value\n")
                for unit in ("fro", "forsvarsmakten"):
                    merged = ub.effective_kv_by_file(unit, secret=True)
                    self.assertEqual(
                        merged["martine.conf"]["martine_openai_api_key"],
                        "sk-test-value",
                    )
                    self.assertEqual(
                        ub.list_effective_sources(unit, secret=True)["martine.conf"],
                        [ub.GLOBAL_BOOTSTRAP_SOURCE],
                    )

    def test_unit_level_secret_overrides_global(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with patch.object(ub, "_state_dir", return_value=root), patch.object(
                ub, "inheritance_chain_root_to_leaf",
                return_value=["fro", "taklabs"],
            ):
                base = ub.global_bootstrap_dir(secret=True)
                base.mkdir(parents=True)
                (base / "martine.conf").write_text("martine_openai_api_key = sk-global\n")
                unit = ub.unit_bootstrap_secrets_d("taklabs")
                unit.mkdir(parents=True)
                (unit / "martine.conf").write_text("martine_openai_api_key = sk-override\n")
                merged = ub.effective_kv_by_file("taklabs", secret=True)
                self.assertEqual(merged["martine.conf"]["martine_openai_api_key"], "sk-override")

    def test_local_import_protects_key_and_destination(self):
        importer = _load_importer()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "martine-api-key"
            source.write_bytes(b"sk-test-never-real-key-value-1234567\n")
            source.chmod(0o664)
            destination = root / "state" / "bootstrap" / "secrets.d" / "martine.conf"
            with patch.object(importer, "_destination", return_value=destination):
                importer.import_key(source)
            self.assertEqual(source.stat().st_mode & 0o777, 0o600)
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
            self.assertEqual(destination.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(
                destination.read_text(),
                "martine_openai_api_key = sk-test-never-real-key-value-1234567\n",
            )


if __name__ == "__main__":
    unittest.main()
