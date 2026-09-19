import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from olive.services.discord_transport import DiscordTransport, SubmissionRejected


class DiscordTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.posts = []
        self.bot = {'bot':True,'id':'9','username':'Fixture Bot'}
        self.channel = {'id':'2','guild_id':'1','type':0,'name':'fixture-channel'}
        self.guild = {'id':'1','name':'Fixture Server'}
        self.failure = None
        self.vault = Mock()
        self.vault.read_for_provider.return_value = 'dummy-secret-never-persist'
        async def request(method,path,token,payload=None):
            if method=='POST':
                self.posts.append(payload)
                if self.failure: raise self.failure
                return {'id':'10','channel_id':'2','content':payload['content'],'author':{'id':'9'}}
            return self.bot if path=='/users/@me' else self.guild if path=='/guilds/1' else self.channel
        self.transport=DiscordTransport(self.temp.name,self.vault,request)
        await self.transport.configure('dummy-secret-never-persist','1','2')
        self.arguments=dict(provider='discord',action_id='request-1',revision=self.transport.status()['revision'],
                            server='Fixture Server',channel='fixture-channel',message='hello')

    async def test_exact_submission_deduplicates_and_excludes_secret(self):
        first=await self.transport.submit(self.arguments)
        self.assertEqual(await self.transport.submit(self.arguments),first)
        self.assertEqual(len(self.posts),1)
        self.assertEqual(self.posts[0]['allowed_mentions'],{'parse':[]})
        self.assertTrue(self.posts[0]['enforce_nonce'])
        for path in Path(self.temp.name).iterdir():
            self.assertNotIn(b'dummy-secret-never-persist',path.read_bytes())
        self.assertNotIn('token',json.dumps(self.transport.status()))

    async def test_uncertain_send_survives_restart_without_replay(self):
        self.failure=TimeoutError('Network interrupted')
        with self.assertRaises(TimeoutError):await self.transport.submit(self.arguments)
        self.assertEqual(self.transport.outcome('request-1'),'uncertain')
        resumed=DiscordTransport(self.temp.name,self.vault,self.transport.request)
        with self.assertRaises(ValueError):await resumed.submit(self.arguments)
        self.assertEqual(len(self.posts),1)

    async def test_rejected_send_is_failed_not_uncertain(self):
        self.failure=SubmissionRejected('HTTP 403')
        with self.assertRaises(SubmissionRejected):await self.transport.submit(self.arguments)
        self.assertEqual(self.transport.outcome('request-1'),'failed')

    async def test_changed_content_identity_revision_and_destination_do_not_send(self):
        for changes in ({'channel':'elsewhere'},{'server':'elsewhere'},{'revision':'stale'}):
            with self.assertRaises(ValueError):await self.transport.submit(dict(self.arguments,**changes))
        self.assertEqual(self.posts,[])
        await self.transport.submit(self.arguments)
        with self.assertRaises(ValueError):await self.transport.submit(dict(self.arguments,message='replacement'))
        self.assertEqual(len(self.posts),1)

    async def test_channel_rename_and_disconnect_fail_closed(self):
        self.channel['name']='renamed'
        with self.assertRaises(ValueError):await self.transport.submit(self.arguments)
        await self.transport.disconnect(True)
        with self.assertRaises(ValueError):await self.transport.submit(self.arguments)
        self.vault.remove.assert_called_once_with('discord-bot')
        self.assertEqual(self.posts,[])

    async def test_personal_account_tokens_rejected_and_connection_test_never_posts(self):
        self.bot['bot']=False
        with self.assertRaises(ValueError):await self.transport.configure('another-dummy-secret-token','1','2')
        self.assertEqual(self.posts,[])

    async def test_cancellation_records_uncertainty(self):
        self.failure=asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):await self.transport.submit(self.arguments)
        self.assertEqual(self.transport.outcome('request-1'),'uncertain')

    async def test_revoked_authority_and_changed_bot_block_before_network_write(self):
        def revoked(): raise PermissionError('Revoked')
        with self.assertRaises(PermissionError):await self.transport.submit(self.arguments,revoked)
        self.assertEqual(self.posts,[])

    async def test_destination_listing_filters_private_channels_by_effective_permissions(self):
        original=self.transport.request
        self.guild['roles']=[{'id':'1','permissions':str((1<<10)|(1<<11))}]
        async def request(method,path,token,payload=None):
            if path=='/users/@me/guilds':return [{'id':'1','name':'Fixture Server'}]
            if path=='/guilds/1/members/9':return {'roles':[]}
            if path=='/guilds/1/channels':return [self.channel,{**self.channel,'id':'3','name':'hidden','permission_overwrites':[{'id':'1','type':0,'deny':str(1<<10),'allow':'0'}]}]
            return await original(method,path,token,payload)
        self.transport.request=request
        self.assertEqual((await self.transport.destinations('1'))['channels'],[{'id':'2','name':'fixture-channel','can_send':True}])
        self.assertEqual(self.posts,[])
        with self.assertRaises(ValueError):await self.transport.select_destination('1','3')
        self.assertEqual(self.transport.outcome('request-1'),'not_attempted')
        self.bot['id']='another-bot'
        with self.assertRaises(ValueError):await self.transport.submit(self.arguments)
        self.assertEqual(self.posts,[])
