"""Desktop OAuth for the existing M4 transports. No credential-bearing tool calls.

Google authorization uses the system browser, loopback state and PKCE. Only the
registered client and refresh credential persist, in the existing OS vault.
"""
import base64
import hashlib
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler
from urllib.error import HTTPError
import ssl

from .mime import addresses
from .store import Conflict

CLIENT_REF = 'mail-' + hashlib.sha256(b'OLIVE Google desktop client').hexdigest()[:32]
SCOPE = 'https://mail.google.com/'
TOKEN_URL = 'https://oauth2.googleapis.com/token'


class OAuthFailure(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise OAuthFailure('OAuth endpoint redirected; authorization stopped')


def request_json(url, fields=None, access_token=None):
    headers={'Accept':'application/json'}
    if access_token:headers['Authorization']='Bearer '+access_token
    data=urlencode(fields).encode() if fields is not None else None
    if data is not None:headers['Content-Type']='application/x-www-form-urlencoded'
    try:
        opener=build_opener(NoRedirect(),HTTPSHandler(context=ssl.create_default_context()))
        with opener.open(Request(url,data=data,headers=headers),timeout=20) as response:
            raw=response.read(64001)
        if len(raw)>64000:raise OAuthFailure('OAuth response exceeds its bound')
        value=json.loads(raw)
        if not isinstance(value,dict):raise OAuthFailure('OAuth response is invalid')
        return value
    except HTTPError as error:
        # Never expose response bodies, authorization codes or tokens in errors.
        if error.code in (400,401,403):raise OAuthFailure('Google authorization expired, was revoked, or requires configuration') from None
        raise OAuthFailure('Google authorization service is unavailable') from None


def validate_token(value):
    token=value.get('access_token')
    if not isinstance(token,str) or not token or len(token)>16000 or any(ord(c)<33 for c in token):
        raise OAuthFailure('Google did not return a usable access token')
    if value.get('token_type','').lower()!='bearer':raise OAuthFailure('Unsupported Google token type')
    if value.get('scope') and SCOPE not in value['scope'].split():raise OAuthFailure('Google Mail permission was not granted')
    lifetime=value.get('expires_in',0)
    if type(lifetime) is not int or lifetime<60:raise OAuthFailure('Google token lifetime is invalid')
    return token,time.monotonic()+min(lifetime,3600)-30


class GoogleAuth:
    def __init__(self,connections):
        self.connections=connections;self.vault=connections.vault
        self.lock=threading.RLock();self.pending=None;self.state='idle';self.result_id=''
        self.cache={};self.closed=False

    def status(self):
        try:self.client();configured=True
        except Exception:configured=False
        with self.lock:return {'configured':configured,'state':self.state,'connection_id':self.result_id,
                              'authentication':'Google desktop OAuth / IMAP and SMTP'}

    def client(self):
        value=json.loads(self.vault.read_for_provider(CLIENT_REF))
        if not isinstance(value,dict) or set(value)!={'client_id','client_secret'}:raise OAuthFailure('Import a registered Google desktop client configuration')
        return value

    def import_client(self,path,guard):
        file=Path(path)
        if not file.is_file() or file.stat().st_size>32000:raise OAuthFailure('Choose the Google desktop-client JSON file')
        raw=file.read_bytes()
        if len(raw)>32000:raise OAuthFailure('Client configuration exceeds its bound')
        value=json.loads(raw).get('installed',{})
        if not isinstance(value,dict):raise OAuthFailure('A registered Desktop app client is required')
        client_id=value.get('client_id','');secret=value.get('client_secret','')
        if not isinstance(client_id,str) or not client_id.endswith('.apps.googleusercontent.com') or len(client_id)>200 or not isinstance(secret,str) or not 1<=len(secret)<=300:
            raise OAuthFailure('A registered Desktop app client is required')
        if value.get('auth_uri')!='https://accounts.google.com/o/oauth2/auth' or value.get('token_uri')!=TOKEN_URL:
            raise OAuthFailure('Client configuration must use official Google endpoints')
        with self.lock:
            if self.pending:raise Conflict('Cancel the current authorization before replacing client configuration')
            guard();self.vault.put(CLIENT_REF,json.dumps({'client_id':client_id,'client_secret':secret}))
        return self.status()

    def begin(self,guard,connection_id=''):
        with self.lock:
            if self.closed or self.pending:raise Conflict('An authorization is already active or the service is closed')
            client=self.client();guard()
            existing=self.connections.get(connection_id) if connection_id else None
            if existing and existing.get('auth_type')!='google_oauth':raise OAuthFailure('Select a Google OAuth account')
            pending={'state':secrets.token_urlsafe(32),'verifier':secrets.token_urlsafe(64),
                     'cancel':threading.Event(),'deadline':time.monotonic()+300,'client':client,'existing':existing}
            owner=self
            class Callback(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_GET(self):
                    parsed=urlsplit(self.path);query=parse_qs(parsed.query)
                    valid=(parsed.path=='/oauth/callback' and len(self.path)<8192 and
                           query.get('state')==[pending['state']] and
                           self.headers.get('Host')==f"127.0.0.1:{pending['server'].server_port}")
                    code=query.get('code',[])
                    if valid and not pending['cancel'].is_set():
                        pending['cancel'].set()
                        try:
                            if query.get('error') or len(code)!=1 or not 1<=len(code[0])<=4096:raise OAuthFailure('Google authorization was cancelled')
                            owner.complete(pending,code[0],guard)
                            message='OLIVE account authorized. Return to OLIVE to enable and test the connection.'
                        except Exception:
                            with owner.lock:owner.state='authorization_failed'
                            message='Authorization did not complete. Return to OLIVE to retry or check setup.'
                        self.send_response(200)
                    else:self.send_response(400);message='Invalid or expired authorization callback.'
                    self.send_header('Content-Type','text/plain; charset=utf-8');self.send_header('Cache-Control','no-store');self.end_headers()
                    try:self.wfile.write(message.encode())
                    except OSError:pass
            class LoopbackServer(HTTPServer):
                def get_request(self):
                    sock,address=super().get_request();sock.settimeout(3);return sock,address
            server=LoopbackServer(('127.0.0.1',0),Callback);server.timeout=.5
            pending['server']=server;pending['redirect']=f'http://127.0.0.1:{server.server_port}/oauth/callback'
            self.pending=pending;self.state='awaiting_browser';self.result_id=''
            def wait():
                try:
                    while not pending['cancel'].is_set() and time.monotonic()<pending['deadline']:server.handle_request()
                finally:
                    server.server_close()
                    with self.lock:
                        if self.state=='awaiting_browser':self.state='expired'
                        if self.pending is pending:self.pending=None
            pending['thread']=threading.Thread(target=wait,daemon=True);pending['thread'].start()
            challenge=base64.urlsafe_b64encode(hashlib.sha256(pending['verifier'].encode()).digest()).rstrip(b'=').decode()
            query={'client_id':client['client_id'],'redirect_uri':pending['redirect'],'response_type':'code','scope':SCOPE,
                   'state':pending['state'],'code_challenge':challenge,'code_challenge_method':'S256','access_type':'offline','prompt':'consent select_account'}
            return {'url':'https://accounts.google.com/o/oauth2/v2/auth?'+urlencode(query),'state':self.state}

    def complete(self,pending,code,guard):
        guard()
        if time.monotonic()>=pending['deadline']:raise OAuthFailure('Authorization expired')
        value=request_json(TOKEN_URL,{**pending['client'],'code':code,'code_verifier':pending['verifier'],
                                     'redirect_uri':pending['redirect'],'grant_type':'authorization_code'})
        token,expires=validate_token(value)
        profile=request_json('https://gmail.googleapis.com/gmail/v1/users/me/profile',access_token=token)
        sender=addresses([profile.get('emailAddress','')])[0]
        refresh=value.get('refresh_token')
        if not isinstance(refresh,str) or not refresh or len(refresh)>1000:raise OAuthFailure('Google did not grant offline authorization')
        credential=json.dumps({**pending['client'],'refresh_token':refresh})
        if len(credential.encode('utf-16-le'))>2500:raise OAuthFailure('Google credential exceeds this vault entry capacity')
        with self.lock:
            if self.pending is not pending or self.state!='awaiting_browser' or self.closed:raise OAuthFailure('Authorization cancelled')
            guard();existing=pending['existing']
            if existing and existing['sender'].casefold()!=sender.casefold():raise OAuthFailure('Google selected a different account; use Add account')
            if existing:
                current=self.connections.get(existing['id'])
                if current['revision']!=existing['revision']:raise Conflict('Account changed during authorization')
            else:
                if any(c.get('auth_type')=='google_oauth' and c.get('sender','').casefold()==sender.casefold() for c in self.connections.list()['items']):
                    raise OAuthFailure('This Google account already exists; use Reauthorize for that account')
                current=self.connections.save({'name':sender,'sender':sender,'username':sender,
                    'smtp':{'host':'smtp.gmail.com','port':465,'tls':'tls'},'imap':{'host':'imap.gmail.com','port':993,'tls':'tls'}})
            current=self.connections.store_secret(current['id'],current['revision'],credential)
            with self.connections.store.transaction() as db:
                body=self.connections.store.body(current);body.update(auth_type='google_oauth',provider='gmail',validated_senders=[sender])
                self.connections.store.save(db,'connection',body,current['id'],current['revision'])
            self.cache[current['id']]=(token,expires,current['credential_ref']);self.result_id=current['id'];self.state='authorized_needs_enable'

    def access_token(self,connection):
        with self.lock:
            def check_revision():
                current=self.connections.get(connection['id'])
                if current['revision']!=connection['revision']:raise Conflict('Account changed during authorization')
            check_revision()
            cached=self.cache.get(connection['id'])
            if cached and cached[1]>time.monotonic() and cached[2]==connection.get('credential_ref'):return cached[0]
            credentials=json.loads(self.vault.read_for_provider(connection['credential_ref']))
            try:
                value=request_json(TOKEN_URL,{**credentials,'grant_type':'refresh_token'})
                token,expires=validate_token(value)
            except OAuthFailure:
                self.cache.pop(connection['id'],None)
                raise
            check_revision()
            if value.get('refresh_token'):
                refresh=value['refresh_token']
                if not isinstance(refresh,str) or len(refresh)>1000:raise OAuthFailure('Invalid refreshed Google credential')
                credentials['refresh_token']=refresh
                self.vault.put(connection['credential_ref'],json.dumps(credentials))
            self.cache[connection['id']]=(token,expires,connection['credential_ref'])
            return token

    def cancel(self):
        with self.lock:
            if self.pending:self.pending['cancel'].set()
            self.state='cancelled'
        return self.status()

    def close(self):
        self.closed=True;self.cancel();self.cache.clear()
