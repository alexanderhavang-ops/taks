from __future__ import annotations

import json
import tempfile
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
            }
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
        self.assertEqual(chans[0]["name"], "GruppL-QQEA")
        self.assertEqual(chans[0]["server_channel_id"], 5)
        self.assertEqual(chans[1]["name"], "PlutL-AQ")
        self.assertEqual(chans[1]["server_channel_id"], 4)

        self.assertEqual(obj["channel_name"], "GruppL-QQEA")
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
