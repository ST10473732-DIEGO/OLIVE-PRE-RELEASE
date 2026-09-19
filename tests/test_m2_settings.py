"""M2 local bridge regressions; temporary profiles, no desktop or model calls."""
import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import AsyncMock

from olive.application.service_container import ServiceContainer
from olive.bridge.host import Host
from olive.bridge.settings import visible, save, schema
from olive.bridge.contracts import validate
from olive.services.backup_service import BackupService


class SettingsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='olive-m2-')
        self.host = Host(lambda event: None)
        self.s = ServiceContainer(self.host.publish, self.host.confirm, data_dir=self.temp.name, migrate=False)
        self.host.services = self.s
        self.chat = self.s.current_chat_id

    async def asyncTearDown(self):
        await self.host.shutdown()
        self.temp.cleanup()

    async def test_settings_roundtrip_does_not_expose_or_overwrite_unknown_fields(self):
        self.s.settings['private_provider_token'] = 'fixture-secret'
        value = await self.host.execute('data.settings', {'chat_id': self.chat})
        self.assertNotIn('fixture-secret', json.dumps(value))
        value['settings']['editor_size'] = 18
        result = await self.host.execute('data.save_settings', {k:v for k,v in value.items() if k != 'model'})
        self.assertEqual(result['settings']['editor_size'], 18)
        self.assertEqual(self.s.settings['private_provider_token'], 'fixture-secret')
        self.assertNotIn('fixture-secret', json.dumps(result))
        self.assertEqual(self.s.settings_repo.load()['editor_size'], 18)
        self.assertEqual(result['settings']['research']['max_searches'], 3)

    async def test_bad_settings_do_not_change_persistence(self):
        before = dict(self.s.settings)
        for patch in [{'editor_size': 200}, {'private_provider_token': 'oops'}, {'research': {'unexpected': 1}}, {'auto_rag': 'yes'}]:
            with self.assertRaises(ValueError):
                save(self.s, self.chat, patch, {}, '', '')
        self.assertEqual(before, self.s.settings)

    async def test_restore_guard_prevents_stale_writes(self):
        self.s.restart_required = True
        for method, args in [('chat.new', {}), ('data.create_project', {'title':'wrong'}), ('runtime.snapshot', {})]:
            with self.assertRaisesRegex(RuntimeError, 'Restart'):
                await self.host.execute(method, args)
        self.s.data.diagnostics = AsyncMock(return_value={'safe':True})
        self.assertEqual(await self.host.execute('data.diagnostics', {}), {'safe':True})
        self.assertEqual(await self.host.execute('runtime.shutdown', {}), {'closing':True})

    async def test_restore_blocks_unsaved_buffers_and_inflight_interpretation(self):
        self.host.buffers['fixture'] = {'text': 'unsaved'}
        with self.assertRaisesRegex(ValueError, 'unsaved'):
            await self.host.execute('data.restore', {'path':'unused', 'confirmed':True})
        self.host.buffers.clear()
        self.s.interaction.interpreting[self.chat] = {'fixture'}
        try:
            with self.assertRaisesRegex(ValueError, 'Stop active work'):
                await self.s.data.restore('unused', confirmed=True)
        finally:
            self.s.interaction.interpreting.clear()

    async def test_permission_mutations_reject_unknown_fields(self):
        before = self.s.permissions.policies()
        for args in [{'permissions': {'invented.permission':'allow'}, 'scopes': []},
                     {'permissions': {}, 'scopes': [{'permission':'filesystem.write','decision':'allow','application':'fixture','extra':'bypass'}]}]:
            with self.assertRaises(ValueError):
                await self.host.execute('data.save_permissions', args)
        self.assertEqual(before, self.s.permissions.policies())

    async def test_local_projects_and_memories_use_existing_repositories(self):
        project = await self.host.execute('data.create_project', {'title':'Fixture project'})
        detail = await self.host.execute('data.project_detail', {'project_id':project['id']})
        self.assertEqual(detail['Overview']['id'], project['id'])
        await self.host.execute('data.memory_save', {'content':'Fixture preference', 'category':'manual'})
        memories = await self.host.execute('data.memories', {'query':'Fixture'})
        self.assertEqual(len(memories), 1)
        await self.host.execute('data.memory_delete', {'memory_id':memories[0]['id']})
        self.assertEqual(await self.host.execute('data.memories', {}), [])

    async def test_contract_rejects_unbounded_unknown_and_untyped_fields(self):
        for args in [{'settings':{}, 'params':{}, 'system_prompt':'', 'chat_id':'c', 'secret':1},
                     {'settings':{'items':list(range(201))}, 'params':{}, 'system_prompt':'', 'chat_id':'c'}]:
            with self.assertRaises(ValueError):
                validate({'v':1, 'id':'fixture', 'method':'data.save_settings', 'args':args})
        self.assertTrue(schema()['fields'])
        self.assertNotIn('token', visible({'settings':{'token':'fixture'}})['settings'])


class SnapshotTests(unittest.TestCase):
    def test_backup_includes_committed_wal_without_touching_source(self):
        with tempfile.TemporaryDirectory(prefix='olive-m2-backup-') as directory:
            root = Path(directory)
            source = root / 'rag.sqlite3'
            with closing(sqlite3.connect(source)) as live:
                live.execute('PRAGMA journal_mode=WAL')
                live.execute('PRAGMA wal_autocheckpoint=0')
                live.execute('CREATE TABLE evidence (value TEXT)')
                live.execute("INSERT INTO evidence VALUES ('committed fixture')")
                live.commit()
                self.assertTrue(Path(str(source)+'-wal').exists())
                archive = BackupService(root).create(components={'rag'})
                with zipfile.ZipFile(archive) as zipped:
                    restored = root / 'restored.sqlite3'
                    restored.write_bytes(zipped.read('data/rag.sqlite3'))
                with closing(sqlite3.connect(restored)) as check:
                    self.assertEqual(check.execute('SELECT value FROM evidence').fetchone()[0], 'committed fixture')
                    self.assertEqual(check.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(live.execute('SELECT COUNT(*) FROM evidence').fetchone()[0], 1)
