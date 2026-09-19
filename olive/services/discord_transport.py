"""Explicitly configured bot submission. Never automates a personal user token."""
import asyncio
import hashlib
import json
import re
import uuid
from pathlib import Path

import httpx

from ..storage.json_store import JsonStore
from ..storage.submission_repository import SubmissionRepository
from .credential_vault import CredentialVault


class SubmissionRejected(RuntimeError):
    pass


class DiscordTransport:
    def __init__(self, directory, vault=None, request=None):
        self.config = JsonStore(Path(directory)/'discord-connection.json')
        self.vault = vault or CredentialVault(directory)
        self.request = request or self._request
        self.lock = asyncio.Lock()
        self.disconnect_requested = False
        self.ledger = SubmissionRepository(Path(directory)/'communication-submissions.sqlite3')

    async def _request(self, method, path, token, payload=None):
        if not re.fullmatch(r'/(?:users/@me(?:/guilds)?|guilds/[0-9]+(?:/channels|/members/[0-9]+)?|channels/[0-9]+(?:/messages)?)', path):
            raise ValueError('Unsupported Discord operation')
        async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False) as client:
            async with client.stream(method, 'https://discord.com/api/v10'+path,
                    headers={'Authorization':'Bot '+token}, json=payload) as response:
                if response.status_code >= 300:
                    if response.status_code == 429:
                        raise SubmissionRejected('Discord rate limited this request. Wait before manually retrying; nothing is replayed automatically.')
                    error = SubmissionRejected if 400 <= response.status_code < 500 else RuntimeError
                    raise error(f'Discord returned HTTP {response.status_code}; no automatic retry was attempted.')
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data)>1_048_576:
                        raise ValueError('Discord response exceeded its limit')
                return json.loads(data)

    def status(self):
        value = self.config.read({})
        if self.disconnect_requested:
            value['enabled'] = False
        return {key:value.get(key) for key in ('enabled','server','channel','guild_id','channel_id','bot_name','bot_id','revision')}

    async def destinations(self, guild_id=''):
        if guild_id and not re.fullmatch(r'[0-9]{1,22}',guild_id):raise ValueError('Invalid server identity')
        async with self.lock:
            config=self.status()
            if not config.get('enabled'):raise ValueError('Configure a bot connection first')
            token=await asyncio.to_thread(self.vault.read_for_provider,'discord-bot')
            bot=await self.request('GET','/users/@me',token)
            if bot.get('bot') is not True or bot.get('id')!=config['bot_id']:raise ValueError('Bot identity changed')
            guilds=await self.request('GET','/users/@me/guilds',token)
            if not isinstance(guilds,list):raise ValueError('Invalid Discord server list')
            if not guild_id:return {'guilds':[{'id':g['id'],'name':g['name']} for g in guilds[:100]],'channels':[],'bounded':len(guilds)>=100}
            if not any(g['id']==guild_id for g in guilds):raise ValueError('The bot cannot access that server')
            guild=await self.request('GET','/guilds/'+guild_id,token)
            member=await self.request('GET',f'/guilds/{guild_id}/members/{bot["id"]}',token)
            channels=await self.request('GET','/guilds/'+guild_id+'/channels',token)
            from .discord_permissions import permissions
            accessible=[]
            for channel in channels[:500]:
                if channel.get('type') not in (0,5):continue
                allowed=permissions(guild,member,channel,bot['id'])
                if allowed & (1<<10):accessible.append({'id':channel['id'],'name':channel['name'],'can_send':bool(allowed & (1<<11))})
            return {'guilds':[{'id':guild_id,'name':guild['name']}],'channels':accessible,'bounded':len(channels)>=500}

    async def select_destination(self,guild_id,channel_id):
        revision=self.status().get('revision')
        available=await self.destinations(guild_id)
        if not any(c['id']==channel_id and c['can_send'] for c in available['channels']):raise ValueError('Choose an accessible writable bot text channel')
        token=await asyncio.to_thread(self.vault.read_for_provider,'discord-bot')
        return await self.configure(token,guild_id,channel_id,expected_revision=revision)

    async def configure(self, token, guild_id, channel_id, expected_revision=None):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{20,2500}', token):
            raise ValueError('Enter an application bot token, not a user token.')
        if any(not re.fullmatch(r'[0-9]{1,22}', item) for item in (guild_id,channel_id)):
            raise ValueError('Server and channel IDs must be Discord numeric IDs.')
        async with self.lock:
            if expected_revision and (self.status().get('revision')!=expected_revision or self.disconnect_requested):
                raise ValueError('The bot connection changed during destination selection')
            bot = await self.request('GET','/users/@me',token)
            if bot.get('bot') is not True:
                raise ValueError('This is not a Discord bot/application identity.')
            guild = await self.request('GET','/guilds/'+guild_id,token)
            channel = await self.request('GET','/channels/'+channel_id,token)
            if guild.get('id') != guild_id or channel.get('guild_id') != guild_id or channel.get('id') != channel_id or channel.get('type') not in (0,5):
                raise ValueError('Choose a text channel in the specified server.')
            await asyncio.to_thread(self.vault.put,'discord-bot',token)
            self.config.write({'schema_version':1,'enabled':True,'guild_id':guild_id,'channel_id':channel_id,
                'server':guild['name'],'channel':channel['name'],'bot_name':bot['username'],'bot_id':bot['id'],'revision':str(uuid.uuid4())})
            self.disconnect_requested = False
            return self.status()

    async def disconnect(self, remove_credentials=False):
        self.disconnect_requested = True
        async with self.lock:
            value = self.config.read({})
            value.update(enabled=False, revision=str(uuid.uuid4()))
            self.config.write(value)
            if remove_credentials:
                await asyncio.to_thread(self.vault.remove,'discord-bot')
            return self.status()

    def resolve(self, entities):
        config = self.status()
        if not config.get('enabled'):
            raise ValueError('Discord delivery is not configured. Add a bot connection for the intended channel in Connections.')
        for key, identity in (('server','guild_id'),('channel','channel_id')):
            supplied = str(entities.get(key,'')).lstrip('#').casefold()
            if supplied not in {str(config[key]).casefold(), str(config[identity])}:
                raise ValueError('The requested destination is outside the configured Discord channel. Check the server and channel names.')
        return config

    def outcome(self, action_id):
        row = self.ledger.get(action_id)
        return row[1] if row else 'not_attempted'

    async def submit(self, arguments, authorize=None):
        async with self.lock:
            config = self.resolve(arguments)
            if arguments.get('revision') != config['revision']:
                raise ValueError('The connection changed. Request the send again.')
            content = arguments['message']
            if not isinstance(content,str) or not 1<=len(content)<=2000:
                raise ValueError('Discord messages must contain 1 to 2000 characters.')
            if not re.fullmatch(r'[A-Za-z0-9-]{1,80}',arguments['action_id']):
                raise ValueError('Invalid communication action identity')
            digest = hashlib.sha256(json.dumps(arguments,sort_keys=True).encode()).hexdigest()
            previous = self.ledger.get(arguments['action_id'])
            if previous:
                if previous[0] == digest and previous[1] == 'accepted':
                    return {'accepted':True,'message_id':previous[2],'replayed':False}
                raise ValueError('This submission may already have been attempted. Review its outcome before requesting another send.')
            token = await asyncio.to_thread(self.vault.read_for_provider,'discord-bot')
            bot = await self.request('GET','/users/@me',token)
            if bot.get('bot') is not True or bot.get('id') != config['bot_id'] or self.disconnect_requested:
                raise ValueError('The sending identity changed or was disconnected. No submission was attempted.')
            channel = await self.request('GET','/channels/'+config['channel_id'],token)
            if self.disconnect_requested:
                raise ValueError('Discord was disconnected before submission.')
            guild = await self.request('GET','/guilds/'+config['guild_id'],token)
            if (channel.get('guild_id') != config['guild_id'] or channel.get('id') != config['channel_id']
                    or channel.get('name') != config['channel'] or guild.get('name') != config['server'] or self.disconnect_requested):
                raise ValueError('The destination could not be revalidated.')
            if authorize:
                authorize()
            self.ledger.reserve(arguments['action_id'],digest)
            # Persist uncertainty before the network write. Cancellation/crash never replays it.
            nonce = hashlib.sha256(arguments['action_id'].encode()).hexdigest()[:24]
            try:
                response = await self.request('POST','/channels/'+config['channel_id']+'/messages',token,
                    {'content':content,'nonce':nonce,'enforce_nonce':True,'allowed_mentions':{'parse':[]}})
            except SubmissionRejected:
                self.ledger.rejected(arguments['action_id'])
                raise
            if (response.get('channel_id') != config['channel_id'] or response.get('content') != content
                    or not response.get('id') or response.get('author',{}).get('id') != config['bot_id']):
                raise ValueError('Discord submission outcome is uncertain. Check the channel before another send.')
            self.ledger.accepted(arguments['action_id'],response['id'])
            return {'accepted':True,'message_id':response['id'],'replayed':False}
