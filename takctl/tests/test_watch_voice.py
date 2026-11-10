import concurrent.futures
from pathlib import Path
import sqlite3
import tempfile
import unittest
from takctl.onboarding import watch_voice as voice
from takctl.onboarding.watch_voice_profile import live_channel_profile
from takctl.onboarding.soldier_card.watch_audio import watch_audio_block


class WatchVoiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / 'private/voice.sqlite'
    def tearDown(self):
        self.temp.cleanup()
    def profile(self, parent):
        self.assertEqual(parent, 'private-card-token')
        return {'_username': 'alex', '_display': 'Alex', 'host': 'test.example', 'port': 64738, 'channels': [{'id': 17, 'name': 'Team'}]}
    def issue(self, now=100):
        return voice.issue('private-card-token', 'alex', path=self.db, now=now)
    def test_single_use_and_separate_credential(self):
        ticket = self.issue(); config = voice.redeem(ticket, self.profile, path=self.db, now=101)
        self.assertEqual(voice.authenticate(config['username'], config['password'], path=self.db, now=102)[1], 'Alex (watch)')
        self.assertIsNone(voice.authenticate(config['username'], 'wrong', path=self.db, now=102))
        self.assertIsNone(voice.authenticate('TW.invalid', config['password'], path=self.db, now=102))
        with self.assertRaises(ValueError): voice.redeem(ticket, self.profile, path=self.db, now=102)
        with sqlite3.connect(self.db) as db:
            stored = str(db.execute('select * from credentials').fetchall())
        self.assertNotIn(config['password'], stored)
        self.assertEqual(self.db.stat().st_mode & 0o777, 0o600)
    def test_expiry_and_parent_revocation(self):
        ticket = self.issue()
        with self.assertRaises(ValueError): voice.redeem(ticket, self.profile, path=self.db, now=280)
        def revoked(_): raise ValueError('Parent card was revoked')
        with self.assertRaises(ValueError): voice.redeem(ticket, revoked, path=self.db, now=101)
    def test_account_cleanup_revokes_credentials_and_pending_tickets(self):
        ticket = self.issue(); config = voice.redeem(ticket, self.profile, path=self.db, now=101)
        other = self.issue(now=102)
        self.assertEqual(voice.revoke('alex', path=self.db), 1)
        self.assertIsNone(voice.authenticate(config['username'], config['password'], path=self.db, now=103))
        with self.assertRaises(ValueError): voice.redeem(other, self.profile, path=self.db, now=103)
    def test_credential_expiry(self):
        config = voice.redeem(self.issue(), self.profile, path=self.db, now=101)
        self.assertIsNone(voice.authenticate(config['username'], config['password'], path=self.db, now=config['credentialExpiresAt']))
    def test_concurrent_redeem_has_one_winner(self):
        ticket = self.issue()
        def use(_):
            try: return voice.redeem(ticket, self.profile, path=self.db, now=101)
            except ValueError: return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: results = list(pool.map(use, range(4)))
        self.assertEqual(sum(result is not None for result in results), 1)
    def test_ticket_rate_limit(self):
        for _ in range(3): self.issue()
        with self.assertRaises(ValueError): self.issue()
        self.issue(now=161)
    def test_failed_profile_does_not_consume_ticket(self):
        ticket=self.issue()
        def wrong(_): return {'_username':'someone-else'}
        with self.assertRaises(ValueError): voice.redeem(ticket, wrong, path=self.db, now=101)
        self.assertTrue(voice.redeem(ticket,self.profile,path=self.db,now=102)['password'])
    def test_channel_ids_are_live_not_topology_guesses(self):
        dbfile=Path(self.temp.name)/'mumble.sqlite'
        with sqlite3.connect(dbfile) as db:
            db.execute('create table channels(server_id integer,channel_id integer,name text)')
            db.execute("insert into channels values(1,77,'Team')")
        vx={'host':'test.example','port':64738,'mission_name':'Test','channels':[{'name':'Team','server_channel_id':1}]}
        self.assertEqual(live_channel_profile('alex',vx,database=dbfile)['channels'][0]['id'],77)
        vx['channels']=[{'name':'Missing'}]
        with self.assertRaises(ValueError): live_channel_profile('alex',vx,database=dbfile)
    def test_localized_button_no_embedded_credentials(self):
        for lang,label in [('en','Play audio code'),('sv','Spela ljudkod')]:
            html=watch_audio_block(base='https://test.example',token='card-secret',lang=lang)
            self.assertIn(label,html);self.assertIn('/watch-voice/ticket',html)
            self.assertNotIn('service-password',html)

if __name__=='__main__':unittest.main()

class WatchVoiceHttpTests(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        from types import SimpleNamespace
        from takctl.api import onboarding_packages as api
        self.temp=tempfile.TemporaryDirectory()
        self.app=FastAPI();self.app.include_router(api.router,prefix='/api')
        self.client=TestClient(self.app,base_url='https://test.example')
        self.patches=[patch.object(voice,'DB_PATH',Path(self.temp.name)/'voice.sqlite'),
                      patch.object(api,'_require_token',return_value=(None,SimpleNamespace(groups=[]),'alex',None)),
                      patch.object(api,'external_base',return_value='https://test.example'),
                      patch.object(api,'load_selection',return_value={}),
                      patch.object(api,'derive_vx_params',return_value={}),
                      patch('takctl.onboarding.watch_voice_profile.live_channel_profile',return_value={'_username':'alex','host':'test.example','port':64738,'channels':[{'id':17,'name':'Team'}]})]
        for patcher in self.patches:patcher.start()
    def tearDown(self):
        for patcher in reversed(self.patches):patcher.stop()
        self.temp.cleanup()
    def test_http_issue_redeem_replay_and_reset(self):
        response=self.client.post('/api/onboarding/cards/card-secret/watch-voice/ticket')
        self.assertEqual(response.status_code,200)
        link=response.json()['url'];self.assertNotIn('card-secret',link)
        ticket=link.split('#')[1]
        response=self.client.post('/api/onboarding/cards/watch-voice/redeem',json={'ticket':ticket})
        self.assertEqual(response.status_code,200)
        data=response.json();self.assertTrue(voice.authenticate(data['username'],data['password']))
        self.assertEqual(self.client.post('/api/onboarding/cards/watch-voice/redeem',json={'ticket':ticket}).status_code,410)
        self.assertIn('no-store',response.headers['cache-control'])
        self.assertEqual(self.client.post('/api/onboarding/cards/card-secret/watch-voice/revoke').json()['revoked'],1)
        self.assertIsNone(voice.authenticate(data['username'],data['password']))
    def test_oversized_and_unknown_ticket(self):
        self.assertEqual(self.client.post('/api/onboarding/cards/watch-voice/redeem',content='x'*513).status_code,413)
        self.assertEqual(self.client.post('/api/onboarding/cards/watch-voice/redeem',json={'ticket':'a'*43}).status_code,410)
    def test_expired_parent_card_prevents_redemption(self):
        from fastapi import HTTPException
        from unittest.mock import patch
        from takctl.api import onboarding_packages as api
        link=self.client.post('/api/onboarding/cards/card-secret/watch-voice/ticket').json()['url']
        with patch.object(api,'_require_token',side_effect=HTTPException(410,'expired')):
            self.assertEqual(self.client.post('/api/onboarding/cards/watch-voice/redeem',json={'ticket':link.split('#')[1]}).status_code,410)

class WatchAuthenticatorTests(unittest.TestCase):
    def test_installer_authenticator_accepts_watch_and_fails_closed(self):
        import ast,sys,types
        from unittest.mock import patch
        root=Path(__file__).resolve().parents[2]
        tree=ast.parse((root/'tak-installer/tak_installer/actions/mumble_server_core.py').read_text())
        script=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='AUTH_SCRIPT' for target in node.targets))
        with tempfile.TemporaryDirectory() as temp, patch.object(voice,'DB_PATH',Path(temp)/'voice.sqlite'):
            ticket=voice.issue('card','alex')
            config=voice.redeem(ticket,lambda _: {'_username':'alex','_display':'Alex'})
            ns={'__name__':'test_authenticator'}
            with patch.dict(sys.modules,{'Ice':types.SimpleNamespace(loadSlice=lambda _:None),'MumbleServer':types.SimpleNamespace(ServerAuthenticator=object)}):
                exec(compile(script,'generated-authenticator.py','exec'),ns)
                ns['log']=lambda _:None
                auth=ns['VoicePinAuthenticator']()
                args=([], '', False)
                identity,name,groups=auth.authenticate(config['username'],config['password'],*args)
                self.assertGreater(identity,0);self.assertEqual(name,'Alex (watch)');self.assertEqual(groups,[])
                self.assertEqual(auth.authenticate(config['username'],'wrong',*args)[0],-1)
                self.assertEqual(auth.authenticate('TW.not-valid',config['password'],*args)[0],-1)
                self.assertEqual(auth.nameToId(config['username']),identity)
                self.assertEqual(auth.idToName(identity),'Alex (watch)')
                voice.revoke('alex')
                self.assertEqual(auth.authenticate(config['username'],config['password'],*args)[0],-1)
