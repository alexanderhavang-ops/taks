import json
import unittest
from martine.security import Principal, authorize, allowed, sanitize


class ChatScopeTests(unittest.TestCase):
    def setUp(self):
        self.user=Principal(username='alice',unit='one',authenticated=True,sender_uid='phone-a',callsign='Alice',device_uids=('phone-a','watch-a'),channels=('Org-one',))
        self.admin=Principal(username='admin',unit='one',admin=True,authenticated=True)

    def test_cross_account_and_cross_device_access_is_denied(self):
        for name,args in [('get_onboarding_diagnostics',{'username':'bob'}),('get_my_connection_events',{'username':'bob'}),
                          ('send_voice_onboarding',{'target_uid':'phone-b'}),('send_voice_onboarding',{'target_uid':'phone-a','channels':['Secret']})]:
            with self.subTest(name=name),self.assertRaises(PermissionError): authorize(name,args,self.user)
        self.assertEqual(authorize('get_onboarding_diagnostics',{},self.user)['username'],'alice')
        self.assertEqual(authorize('send_voice_onboarding',{'target_uid':'watch-a'},self.user)['target_uid'],'watch-a')

    def test_admin_and_development_boundaries(self):
        for name in ('business_read','marti_read','read_diagnostic_log','product_health','request_business_change'):
            self.assertFalse(allowed(name,self.user));self.assertTrue(allowed(name,self.admin))
        for actor in (self.user,self.admin,Principal()):
            for name in ('shell_exec','deploy','fs_write','ensure_martine_state_dirs','martine_live_inference_test'):
                self.assertFalse(allowed(name,actor))
        self.assertFalse(allowed('read_diagnostic_log',Principal(callsign='admin',sender_uid='ADMIN')))

    def test_nested_tool_json_credentials_and_card_links_are_redacted(self):
        value={'password':'actual-private-value','text':json.dumps({'api_key':'provider-private-value','ok':True}),
               'raw_json':'prefix \"password\": \"json-secret\", \"a\":1',
               'logs':'Authorization: Bearer abcdef\npassword="hidden value"\n/api/onboarding/cards/opaque-token/packages'}
        result=json.dumps(sanitize(value))
        for secret in ('actual-private-value','provider-private-value','abcdef','hidden value','opaque-token','json-secret'):
            self.assertNotIn(secret,result)

    def test_role_change_separates_conversation_scope(self):
        self.assertNotEqual(self.user.session_scope,Principal(username='alice',unit='one',admin=True,authenticated=True).session_scope)


if __name__=='__main__':unittest.main()
