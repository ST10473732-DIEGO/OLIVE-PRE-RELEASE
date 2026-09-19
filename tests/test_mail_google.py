"""Synthetic desktop OAuth boundary tests. No Google account is contacted."""
import base64
import hashlib
import http.client
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit,parse_qs,urlencode
from olive.mail.connections import Connections
from olive.mail.store import MailStore
from olive.mail.google_auth import GoogleAuth,CLIENT_REF,SCOPE,OAuthFailure
from tests.test_mail_local import DummyVault


class GoogleAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.vault=DummyVault();self.store=MailStore(self.root/'mail.sqlite3')
        self.connections=Connections(self.store,self.vault);self.auth=GoogleAuth(self.connections);self.connections.google=self.auth
        self.vault.put(CLIENT_REF,json.dumps({'client_id':'fixture.apps.googleusercontent.com','client_secret':'synthetic-client'}))

    def tearDown(self):
        pending=self.auth.pending;self.auth.close()
        if pending:pending['thread'].join(3)
        self.temp.cleanup()

    def callback(self,url,state,code='synthetic-code'):
        callback=urlsplit(parse_qs(urlsplit(url).query)['redirect_uri'][0])
        client=http.client.HTTPConnection(callback.hostname,callback.port,timeout=3)
        try:
            client.request('GET',callback.path+'?'+urlencode({'state':state,'code':code}))
            response=client.getresponse();body=response.read();return response.status,body
        finally:client.close()

    def test_loopback_pkce_wrong_state_correct_account_and_vault_only(self):
        grant=self.auth.begin(lambda:None);pending=self.auth.pending;params=parse_qs(urlsplit(grant['url']).query)
        expected=base64.urlsafe_b64encode(hashlib.sha256(pending['verifier'].encode()).digest()).rstrip(b'=').decode()
        self.assertEqual(params['code_challenge'],[expected]);self.assertEqual(params['scope'],[SCOPE])
        with patch('olive.mail.google_auth.request_json') as network:
            self.assertEqual(self.callback(grant['url'],'wrong')[0],400);network.assert_not_called()
            network.side_effect=[{'access_token':'synthetic-access','refresh_token':'synthetic-refresh','token_type':'Bearer','expires_in':3600,'scope':SCOPE},{'emailAddress':'one@example.invalid'}]
            self.assertEqual(self.callback(grant['url'],params['state'][0])[0],200)
        pending['thread'].join(3)
        record=self.connections.get(self.auth.result_id)
        self.assertFalse(record['enabled']);self.assertEqual(record['sender'],'one@example.invalid')
        self.assertEqual(record['validated_senders'],['one@example.invalid'])
        self.assertEqual(record['auth_type'],'google_oauth')
        self.assertIn('synthetic-refresh',self.vault.read_for_provider(record['credential_ref']))
        with self.store.transaction() as db:
            stored=' '.join(r[0] for r in db.execute('SELECT body FROM records'))
        self.assertNotIn('synthetic-access',stored);self.assertNotIn('synthetic-refresh',stored);self.assertNotIn('synthetic-client',stored)
        self.assertEqual(self.connections.secret(record),'synthetic-access')
        with self.assertRaises(ValueError):self.connections.save({'name':'Redirect','sender':record['sender'],'username':record['username'],'smtp':{'host':'attacker.invalid','port':465,'tls':'tls'}},record['id'],record['revision'])

    def test_cancel_and_denial_do_not_create_accounts(self):
        def deny():raise PermissionError('denied')
        with self.assertRaises(PermissionError):self.auth.begin(deny)
        self.assertIsNone(self.auth.pending)
        grant=self.auth.begin(lambda:None);pending=self.auth.pending
        self.auth.cancel();pending['thread'].join(3)
        self.assertEqual(self.connections.list()['items'],[])
        with patch('olive.mail.google_auth.request_json') as network:
            with self.assertRaises(OAuthFailure):
                # Cancelling during an in-flight token exchange must fail before persistence.
                network.side_effect=[{'access_token':'synthetic-access','refresh_token':'synthetic-refresh','token_type':'Bearer','expires_in':3600},{'emailAddress':'one@example.invalid'}]
                self.auth.complete(pending,'synthetic-code',lambda:None)
        self.assertEqual(self.connections.list()['items'],[])
        self.assertNotIn('code=',grant['url'])

    def test_import_requires_desktop_config_and_mail_scope(self):
        path=self.root/'client.json';path.write_text(json.dumps({'web':{'client_id':'wrong'}}))
        with self.assertRaises(OAuthFailure):self.auth.import_client(path,lambda:None)
        path.write_text(json.dumps({'installed':{'client_id':'fixture.apps.googleusercontent.com','client_secret':'synthetic','auth_uri':'https://accounts.google.com/o/oauth2/auth','token_uri':'https://oauth2.googleapis.com/token'}}))
        self.assertTrue(self.auth.import_client(path,lambda:None)['configured'])
        from olive.mail.google_auth import validate_token
        with self.assertRaises(OAuthFailure):validate_token({'access_token':'fake','token_type':'Bearer','expires_in':3600,'scope':'profile'})

    def test_refresh_rotation_and_account_revision_invalidate_cached_access(self):
        c=self.connections.save({'name':'Synthetic OAuth','sender':'one@example.invalid','username':'one@example.invalid','smtp':{'host':'smtp.gmail.com','port':465,'tls':'tls'}})
        credential={'client_id':'fixture.apps.googleusercontent.com','client_secret':'synthetic-client','refresh_token':'synthetic-refresh'}
        c=self.connections.store_secret(c['id'],c['revision'],json.dumps(credential))
        with patch('olive.mail.google_auth.request_json',return_value={'access_token':'synthetic-access','token_type':'Bearer','expires_in':3600,'refresh_token':'rotated-synthetic'}) as network:
            self.assertEqual(self.auth.access_token(c),'synthetic-access')
            self.assertEqual(self.auth.access_token(c),'synthetic-access');self.assertEqual(network.call_count,1)
        self.assertEqual(json.loads(self.vault.read_for_provider(c['credential_ref']))['refresh_token'],'rotated-synthetic')
        self.connections.change_state(c['id'],c['revision'],False,remove_credentials=True)
        with self.assertRaises(ValueError):self.auth.access_token(c)
