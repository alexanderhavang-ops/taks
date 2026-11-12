from types import SimpleNamespace
import json
import os
import unittest
from unittest.mock import patch

from martine.security import Principal, allowed, authorize, PUBLIC
from takctl.services.geochat_delivery import voice_delivery_principal

SESSION = {'clientUid': 'phone-a', 'username': 'alice', 'callsign': 'Alice', 'protocol': 'tls'}
ACCOUNT = {'username': 'alice', 'unit': 'one', 'admin': True, 'authenticated': True, 'transport': 'geochat'}


class GeoChatVoiceTests(unittest.TestCase):
    def resolve(self, rows=None, selection=None):
        with patch('takctl.services.marti_api.marti_json', return_value={'data': [SESSION] if rows is None else rows}), patch('takctl.services.business_access.account_actor', return_value=ACCOUNT), patch('takctl.onboarding.selection.load_selection', return_value=selection or {'channels': {'available': ['Org-one']}}):
            return voice_delivery_principal('phone-a')

    def test_live_destination_enables_voice_without_authenticating_payload_or_admin(self):
        actor = Principal(**self.resolve())
        self.assertFalse(actor.authenticated)
        self.assertFalse(actor.admin)
        self.assertTrue(actor.delivery_verified)
        self.assertEqual(actor.device_uids, ('phone-a',))
        self.assertTrue(allowed('send_voice_onboarding', actor))
        for name in ('get_onboarding_diagnostics', 'read_diagnostic_log', 'network_capture_start',
                     'request_business_change', 'send_plugin_onboarding', 'shell_exec'):
            self.assertFalse(allowed(name, actor), name)
        self.assertFalse(allowed('send_voice_onboarding', Principal(sender_uid='phone-a', callsign='Alice')))

    def test_offline_duplicate_anonymous_and_unbound_destinations_fail_closed(self):
        for rows in ([], [SESSION, SESSION], [SESSION | {'username': ''}],
                     [SESSION | {'protocol': 'udp'}], [SESSION | {'clientUid': 'phone-b'}]):
            with self.subTest(rows=rows), self.assertRaises(PermissionError):
                self.resolve(rows)

    def test_destination_cannot_select_other_device_channels_or_server_credentials(self):
        actor = Principal(**self.resolve())
        clean = authorize('send_voice_onboarding', {}, actor)
        self.assertEqual(clean['target_uid'], 'phone-a')
        self.assertEqual(clean['target_callsign'], 'Alice')
        self.assertEqual(clean['channels'], ['Org-one'])
        for values in ({'target_uid': 'phone-b'}, {'target_callsign': 'Bob'},
                       {'channels': ['Secret']}, {'channels_csv': 'Secret'},
                       {'mumble_host': 'other.example'}, {'server_password': 'override'}):
            with self.subTest(values=values), self.assertRaises(PermissionError):
                authorize('send_voice_onboarding', values, actor)
        with self.assertRaises(PermissionError):
            authorize('send_voice_onboarding', {}, Principal(**(self.resolve() | {'channels': ()})))

    def test_channels_come_from_account_context_when_selection_has_no_explicit_list(self):
        with patch('takctl.onboarding.voice_topology.derive_voice_topology', return_value={'seed_channels': ['Org-derived']}) as topology:
            actor = self.resolve(selection={'ctx': {'unit': 'one', 'policy_id': 'generic'}})
        self.assertEqual(actor['channels'], ('Org-derived',))
        topology.assert_called_once_with(None, {'unit': 'one', 'policy_id': 'generic'})

    def test_ingress_passes_verified_destination_and_isolates_history(self):
        from martine.chat.cot_tls_client import build_atak_chat_xml, handle_one_message
        xml = build_atak_chat_xml(chat_uid='phone-a', callsign='Spoofed',
            to_uid='ANDROID-MARTINE', to_callsign='Martine', message='Onboard me for voice')
        actor = self.resolve()
        with patch('takctl.services.geochat_delivery.voice_delivery_principal', return_value=actor), patch('martine.agent.simple_agent.run_once', return_value={'answer': 'Sent'}) as run, patch('martine.chat.cot_tls_client.send_event'):
            handle_one_message(object(), SimpleNamespace(chat_uid='ANDROID-MARTINE', callsign='Martine'), xml)
        self.assertEqual(run.call_args.kwargs['principal'], actor)
        self.assertEqual(run.call_args.kwargs['conversation_id'], 'geochat:phone-a')

    def test_agent_catalog_includes_voice_but_excludes_account_and_admin_tools(self):
        from martine_server.agent_loop import _allowed_tools
        context = SimpleNamespace(client='martine_chat', extras={'principal': self.resolve()})
        self.assertEqual(set(_allowed_tools(context)), set(PUBLIC) | {'send_voice_onboarding'})
        context.extras = {}
        self.assertNotIn('send_voice_onboarding', _allowed_tools(context))

    def test_bad_callsign_never_becomes_a_package_path(self):
        actor = self.resolve(rows=[SESSION | {'callsign': '../../other'}])
        self.assertEqual(actor['callsign'], 'alice')

    def test_real_scoped_voice_tool_uses_verified_destination_and_assigned_channels(self):
        from martine.mcp_server import fastmcp_app
        actor = self.resolve()
        with patch.dict(os.environ, {'MARTINE_AUTH_CONTEXT': json.dumps(actor)}), patch.object(fastmcp_app, 'send_voice_onboarding', return_value={'ok': True, 'server_password': 'never-return-this'}) as backend:
            result = fastmcp_app.send_voice_onboarding_tool()
            self.assertTrue(result['ok'])
            self.assertEqual(result['server_password'], '[REDACTED]')
            self.assertEqual(backend.call_args.kwargs['target_uid'], 'phone-a')
            self.assertEqual(backend.call_args.kwargs['target_callsign'], 'Alice')
            self.assertEqual(backend.call_args.kwargs['channels'], ['Org-one'])
            with self.assertRaises(PermissionError):
                fastmcp_app.send_voice_onboarding_tool(target_uid='other-phone')

    def test_certificate_passwords_have_no_builtin_fallback(self):
        from martine.chat import cot_tls_client
        with patch.object(cot_tls_client, '_read_simple_kv', return_value={}), patch.object(cot_tls_client.Path, 'read_text', side_effect=FileNotFoundError):
            self.assertEqual(cot_tls_client._cert_password_candidates(), [None])
