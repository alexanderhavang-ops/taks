"""Martine use-case regressions. Run on an installed node, without API calls.

This suite tests the actual TAK CoT codec, local MCP tool transport and PDF
reference retrieval. It does not rely on a paid model response.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class CoTUseCases(unittest.TestCase):
    def test_send_direct_geochat_and_xml_escaping(self):
        from martine.chat.cot_tls_client import build_atak_chat_xml
        xml = build_atak_chat_xml(
            chat_uid="ANDROID-MARTINE", callsign="Martine",
            to_uid="ANDROID-ALEX", to_callsign="Alex",
            message="Hello & welcome <Alex>",
        )
        root = ET.fromstring(xml)
        self.assertEqual(root.attrib["type"], "b-t-f")
        self.assertEqual(root.find("detail/remarks").text, "Hello & welcome <Alex>")
        self.assertEqual(root.find("detail/remarks").attrib["to"], "ANDROID-ALEX")
        self.assertEqual(root.find("detail/marti/dest").attrib["callsign"], "Alex")

    def test_ingress_routing_and_reply_uses_sender_uid(self):
        from martine.chat.cot_tls_client import (
            build_atak_chat_xml, handle_one_message, parse_chat_xml,
        )
        request = build_atak_chat_xml(
            chat_uid="ANDROID-ALEX", callsign="Alex",
            to_uid="ANDROID-MARTINE", to_callsign="Martine",
            message="Where is Bravo?",
        )
        parsed = parse_chat_xml(request)
        self.assertEqual(parsed["from_uid"], "ANDROID-ALEX")
        self.assertEqual(parsed["to_uid"], "ANDROID-MARTINE")
        calls = []
        fake = lambda q, **kw: calls.append((q, kw)) or {
            "ok": True, "answer": "Bravo is 200m north.", "run_id": "test",
        }
        events = []
        cfg = SimpleNamespace(callsign="Martine", chat_uid="ANDROID-MARTINE")
        with patch("martine.agent.simple_agent.run_once", fake), patch(
            "martine.chat.cot_tls_client.send_event",
            side_effect=lambda sock, xml: events.append(xml),
        ):
            handle_one_message(object(), cfg, request)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]["sender_uid"], "ANDROID-ALEX")
        self.assertEqual(ET.fromstring(events[0]).find("detail/remarks").attrib["to"], "ANDROID-ALEX")

    def test_unaddressed_message_does_not_invoke_agent(self):
        from martine.chat.cot_tls_client import build_atak_chat_xml, handle_one_message
        request = build_atak_chat_xml(
            chat_uid="ANDROID-BOB", callsign="Bob",
            to_uid="ANDROID-CHARLIE", to_callsign="Charlie",
            message="Not for Martine",
        )
        cfg = SimpleNamespace(callsign="Martine", chat_uid="ANDROID-MARTINE")
        with patch("martine.agent.simple_agent.run_once") as run:
            handle_one_message(object(), cfg, request)
        run.assert_not_called()


class DocumentUseCases(unittest.TestCase):
    def test_uploaded_pdf_chunks_and_context(self):
        from martine.tools import docs_ref
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            registry = root / "registry" / "docs.json"
            chunks = root / "derived" / "doc-tactics" / "chunks.jsonl"
            registry.parent.mkdir(parents=True)
            chunks.parent.mkdir(parents=True)
            registry.write_text(json.dumps({"items": [
                {"doc_id": "doc-tactics", "title": "Tactics Manual",
                 "status": "ready", "active": True, "chunk_count": 2},
                {"doc_id": "doc-hidden", "title": "Restricted Old Manual",
                 "status": "ready", "active": False},
            ]}), encoding="utf-8")
            chunks.write_text("\n".join(json.dumps(row) for row in [
                {"doc_id": "doc-tactics", "chunk_id": "c1",
                 "title": "Tactics Manual", "text": "Bravo patrol reports from the north."},
                {"doc_id": "doc-tactics", "chunk_id": "c2",
                 "title": "Tactics Manual", "text": "Use the radio for safety checks."},
            ]) + "\n", encoding="utf-8")
            with patch.object(docs_ref, "REGISTRY_PATH", registry), patch.object(
                docs_ref, "DERIVED_ROOT", root / "derived"
            ):
                docs = docs_ref.list_reference_docs()
                self.assertEqual(docs["count"], 1)
                hits = docs_ref.search_reference_docs(query="Bravo patrol")
                self.assertEqual(hits["count"], 1)
                self.assertEqual(hits["items"][0]["chunk_id"], "c1")
                context = docs_ref.get_reference_doc_context(
                    doc_id="doc-tactics", chunk_id="c1", window=1
                )
                self.assertTrue(context["ok"])
                self.assertIn("Bravo", json.dumps(context))

    def test_missing_document_is_reported_not_invented(self):
        from martine.tools import docs_ref
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "registry").mkdir()
            (root / "registry" / "docs.json").write_text('{"items":[]}')
            with patch.object(docs_ref, "REGISTRY_PATH", root / "registry" / "docs.json"), patch.object(
                docs_ref, "DERIVED_ROOT", root / "derived"
            ):
                result = docs_ref.get_reference_doc_context(doc_id="none", chunk_id="c1")
                self.assertFalse(result["ok"])


class MCPUseCases(unittest.TestCase):
    def test_real_stdio_tool_discovery_and_clock(self):
        """Calls the same child-process FastMCP server used by the new agent."""
        from martine.mcp_server.client import _list_tools_async, _call_tool_async
        tools = asyncio.run(_list_tools_async())
        names = {t["name"] for t in tools}
        required = {
            "ping", "get_current_time", "get_contact_status",
            "get_my_position", "get_nearest_friendly",
            "route_between_points", "send_voice_onboarding",
            "send_plugin_onboarding", "send_map_onboarding",
            "list_reference_docs", "search_reference_docs",
            "search_reference_docs_semantic", "get_reference_doc_context",
            "list_reference_doc_sections", "get_reference_section",
        }
        self.assertFalse(required - names, f"Missing MCP tools: {required - names}")
        response = asyncio.run(_call_tool_async("get_current_time"))
        self.assertTrue(response["ok"])
        self.assertFalse(response["is_error"])


if __name__ == "__main__":
    unittest.main()
