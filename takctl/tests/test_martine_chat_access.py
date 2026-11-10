import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from takctl.web.api.martine import router
from takctl.services import martine_chat as chat
from takctl.services import business_diagnostics as diagnostics

ALICE={'username':'alice','unit':'one','authenticated':True,'admin':False,'transport':'web'}
BOB={**ALICE,'username':'bob'}
ADMIN={**ALICE,'username':'admin','admin':True}


class ChatAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.env=patch.dict(os.environ,{'MARTINE_CHAT_DB':str(Path(self.temp.name)/'chat.sqlite3')});self.env.start();self.addCleanup(self.env.stop)

    def test_other_users_jobs_history_and_actions_are_inaccessible(self):
        with chat.database() as db:
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?)',('job',chat.scope(ALICE),'main',0,'done','private question',json.dumps({'answer':'private answer'})))
        self.assertEqual(len(chat.history(ALICE)['messages']),2)
        self.assertEqual(chat.history(BOB)['messages'],[])
        with self.assertRaises(PermissionError):chat.job(BOB,'job')
        with self.assertRaises(PermissionError):chat.confirm(ALICE,'action')
        with self.assertRaises(PermissionError):diagnostics.onboarding(ALICE,'bob')
        with self.assertRaises(PermissionError):diagnostics.log_tail(ALICE,'voice_auth')

    def test_human_approval_is_bound_to_owner_and_cannot_be_replayed(self):
        action=chat.propose_change(ADMIN,'mumble','channel_create',{'name':'test','parent':0})['action_id']
        other={**ADMIN,'username':'other-admin'}
        with self.assertRaises(PermissionError):chat.confirm(other,action)
        with patch('takctl.services.business_services.call',return_value={'ok':True}) as native,patch.object(chat,'runtime',return_value=(None,lambda v:v)):
            self.assertTrue(chat.confirm(ADMIN,action)['ok'])
            with self.assertRaises(PermissionError):chat.confirm(ADMIN,action)
            native.assert_called_once()

    def test_web_actor_is_not_taken_from_model_or_request_body(self):
        app=FastAPI();app.include_router(router);client=TestClient(app)
        with patch('takctl.web.api.martine.request_actor',return_value=ALICE),patch.object(chat,'submit',return_value={'job_id':'safe'}) as submit:
            r=client.post('/api/martine/ask',headers={'X-TAKS-Chat':'1'},json={'message':'help','principal':ADMIN,'admin':True,'username':'bob'})
            self.assertEqual(r.status_code,200);self.assertEqual(submit.call_args.args[0],ALICE)
            self.assertEqual(client.post('/api/martine/ask',json={'message':'help'}).status_code,403)
        with patch('takctl.web.api.martine.request_actor',side_effect=PermissionError):
            self.assertEqual(client.get('/api/martine/history').status_code,401)

    def test_trace_paths_are_not_exposed_even_to_authenticated_users(self):
        app=FastAPI();app.include_router(router);client=TestClient(app)
        with patch('takctl.web.api.martine.request_actor',return_value=ALICE):
            self.assertEqual(client.get('/api/martine/runs/some-other-run/events').status_code,410)


if __name__=='__main__':unittest.main()
