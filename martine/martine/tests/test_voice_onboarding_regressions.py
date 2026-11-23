from __future__ import annotations

import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


class VoiceOnboardingRegressionTests(unittest.TestCase):
    def test_import_chain_is_intact(self) -> None:
        import martine.tools.voice_onboarding_common as common
        import martine.tools.voice_onboarding_delivery as delivery
        import martine.tools.voice_onboarding_package as package
        import martine.tools.voice_onboarding_db as db
        import martine.tools.voice_onboarding as root

        self.assertTrue(hasattr(common, "_multipart_body"))
        self.assertTrue(hasattr(common, "_mtls_context"))
        self.assertTrue(hasattr(common, "_parse_upload_hash"))
        self.assertTrue(callable(root.send_voice_onboarding))
        self.assertIsNotNone(delivery)
        self.assertIsNotNone(package)
        self.assertIsNotNone(db)

    def test_derive_vx_params_uses_topology_channel_ids(self) -> None:
        from takctl.onboarding.vx import derive_vx_params

        sel = {
            "ctx": {
                "unit": "46hvbat",
                "callsign": "EAQQ1",
                "battalion_fal": "VQ",
                "company": "Q",
                "platoon": "A",
                "group": "E",
            },
            "channels": {"selected": ["GruppL-EAQQ", "PlutL-AQ"]},
        }

        obj = derive_vx_params(
            username="EAQQ1",
            groups=["46hvbat"],
            selection=sel,
            base="https://46hvbat.tak-hv-sandbox.se",
        )

        self.assertEqual(obj["mission_name"], "Samband-46hvbat")
        self.assertEqual(obj["package_name"], "EAQQ1_46hvbat")

        chans = obj["channels"]
        self.assertEqual(chans[0]["name"], "GruppL-EAQQ")
        self.assertEqual(chans[0]["server_channel_id"], 5)
        self.assertEqual(chans[1]["name"], "PlutL-AQ")
        self.assertEqual(chans[1]["server_channel_id"], 4)

        self.assertEqual(obj["channel_name"], "GruppL-EAQQ")
        self.assertEqual(obj["server_channel_id"], 5)

    def test_write_vx_mission_zip_preserves_multi_channel_ids(self) -> None:
        from takctl.onboarding.vx import write_vx_mission_zip

        with tempfile.TemporaryDirectory(prefix="vx-regression-") as td:
            out = Path(td) / "voice.zip"

            write_vx_mission_zip(
                out,
                package_name="EAQQ1_46hvbat",
                mission_name="Samband-46hvbat",
                channels=[
                    {
                        "name": "GruppL-QQEA",
                        "subtitle": "GruppL-QQEA",
                        "server_channel_id": 5,
                    },
                    {
                        "name": "PlutL-AQ",
                        "subtitle": "PlutL-AQ",
                        "server_channel_id": 4,
                    },
                ],
                host="46hvbat.tak-hv-sandbox.se",
                port=64738,
            )

            self.assertTrue(out.is_file())

            with zipfile.ZipFile(out, "r") as zf:
                names = zf.namelist()
                self.assertIn("MANIFEST/manifest.xml", names)

                json_name = [n for n in names if n != "MANIFEST/manifest.xml" and not n.endswith("_proto")][0]
                payload = json.loads(zf.read(json_name).decode("utf-8"))

            channels = payload["channels"]
            self.assertEqual(len(channels), 2)

            self.assertEqual(channels[0]["name"], "GruppL-QQEA")
            self.assertEqual(channels[0]["serverChannelId"], 5)

            self.assertEqual(channels[1]["name"], "PlutL-AQ")
            self.assertEqual(channels[1]["serverChannelId"], 4)

    def test_martine_package_uses_mumble_channel_ids(self) -> None:
        from martine.tools.voice_onboarding_package import _render_voice_package

        with tempfile.TemporaryDirectory(prefix="martine-vx-regression-") as td:
            state_dir = Path(td)

            with patch(
                "martine.tools.voice_onboarding_package._read_mumble_channel_ids",
                return_value={"GruppL-QQEA": 5, "PlutL-AQ": 4},
            ):
                rendered = _render_voice_package(
                    target_callsign="EAQQ1",
                    target_uid="ANDROID-b99979203eda04c1",
                    sender_uid="ANDROID-MARTINE",
                    sender_callsign="Martine",
                    node_name="46hvbat",
                    mission_label="Samband-46hvbat",
                    fqdn="46hvbat.tak-hv-sandbox.se",
                    voice_port=64738,
                    channels=["GruppL-QQEA", "PlutL-AQ"],
                    server_password="dummy",
                    state_dir=state_dir,
                )

            pkg = Path(rendered["package_path"])
            self.assertTrue(pkg.is_file())

            with zipfile.ZipFile(pkg, "r") as zf:
                names = zf.namelist()
                self.assertIn("MANIFEST/manifest.xml", names)

                json_name = [n for n in names if n != "MANIFEST/manifest.xml" and not n.endswith("_proto")][0]
                payload = json.loads(zf.read(json_name).decode("utf-8"))

            channels = payload["channels"]
            self.assertEqual(len(channels), 2)

            self.assertEqual(channels[0]["name"], "GruppL-QQEA")
            self.assertEqual(channels[0]["serverChannelId"], 5)

            self.assertEqual(channels[1]["name"], "PlutL-AQ")
            self.assertEqual(channels[1]["serverChannelId"], 4)

    def test_martine_refuses_to_guess_a_missing_channel_id(self) -> None:
        from martine.tools.voice_onboarding_package import _resolve_channel_name_and_id

        with self.assertRaisesRegex(ValueError, "is missing"):
            _resolve_channel_name_and_id("Team", {"Other team": 1})

    def test_self_service_uses_saved_selection_when_device_callsign_changed(self) -> None:
        from martine.tools.voice_onboarding import _channels_from_identity

        account = SimpleNamespace(authenticated=True, username="member", device_uids=("device",))
        security = SimpleNamespace(current_principal=lambda: account)
        selection = {"ctx": {}, "channels": {"selected": ["Assigned"]}}
        with (
            patch.dict(sys.modules, {"martine.security": security}),
            patch("martine.tools.voice_onboarding.load_selection", return_value=selection) as load,
        ):
            self.assertEqual(_channels_from_identity("Different callsign", "device"), ["Assigned"])
            load.assert_called_once_with("member")

    def test_soldier_card_retains_all_assigned_channels_and_live_ids(self) -> None:
        from takctl.api.onboarding_packages import _write_vx_package

        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "vx.zip"
            params = {"package_name": "Voice", "mission_name": "Mission", "host": "node.example", "port": 64738}
            with (
                patch("takctl.api.onboarding_packages.load_selection", return_value={}),
                patch("takctl.api.onboarding_packages.derive_vx_params", return_value=params),
                patch(
                    "takctl.onboarding.watch_voice_profile.live_channel_profile",
                    return_value={"channels": [{"name": "First", "id": 77}, {"name": "Second", "id": 42}]},
                ),
            ):
                _write_vx_package(out, "member", SimpleNamespace(groups=[]), base="https://node.example")

            with zipfile.ZipFile(out) as archive:
                payload_path = next(name for name in archive.namelist()
                                    if not name.startswith("MANIFEST/") and not name.endswith("_proto"))
                channels = json.loads(archive.read(payload_path))["channels"]
            self.assertEqual([(channel["name"], channel["serverChannelId"]) for channel in channels],
                             [("First", 77), ("Second", 42)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
