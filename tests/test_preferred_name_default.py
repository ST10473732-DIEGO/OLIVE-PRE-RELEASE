"""New profiles carry no owner-specific name; a stored preferred name is never changed."""
import json
from pathlib import Path
import tempfile
import unittest

from olive.application.service_container import ServiceContainer
from olive.bridge.settings import FIELDS
from olive.storage.settings_repository import SettingsRepository


class PreferredNameDefaultTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)  # Cleanups run LIFO: services shut down first.
        self.profile = Path(self.temp.name)

    async def container(self):
        services = ServiceContainer(lambda *a: None, None, data_dir=self.profile, migrate=False)
        self.addAsyncCleanup(services.shutdown)
        return services

    async def test_new_profile_has_no_preferred_name(self):
        services = await self.container()
        self.assertEqual(services.settings['preferred_name'], '')
        field = next(f for f in FIELDS if f['key'] == 'preferred_name')
        self.assertEqual(field['default'], '')
        # The default is not written back as anybody's name.
        services.settings_repo.save(services.settings)
        self.assertEqual(json.loads((self.profile / 'settings.json').read_text())['preferred_name'], '')

    async def test_no_owner_name_anywhere_in_defaults(self):
        services = await self.container()
        self.assertNotIn('Diego', json.dumps(services.settings))
        self.assertNotIn('Diego', json.dumps(FIELDS))
        pipeline = services.chat_service.pipeline
        self.assertEqual(pipeline.preferences().get('preferred_name'), '')

    async def test_existing_stored_name_is_preserved_through_load_and_save(self):
        (self.profile / 'settings.json').write_text(json.dumps({'preferred_name': 'Diego', 'theme': 'Dark'}))
        services = await self.container()
        self.assertEqual(services.settings['preferred_name'], 'Diego')
        services.settings_repo.save(services.settings)
        self.assertEqual(json.loads((self.profile / 'settings.json').read_text())['preferred_name'], 'Diego')

    async def test_a_deliberately_cleared_name_stays_cleared(self):
        (self.profile / 'settings.json').write_text(json.dumps({'preferred_name': ''}))
        self.assertEqual(SettingsRepository(self.profile / 'settings.json', self.profile / 'd.json',
                                            self.profile / 'a.json').load()['preferred_name'], '')
        services = await self.container()
        self.assertEqual(services.settings['preferred_name'], '')

    async def test_legacy_migration_never_rewrites_a_stored_name(self):
        from unittest.mock import patch
        from olive.storage import migration
        legacy = self.profile / 'legacy'
        legacy.mkdir()
        (legacy / 'current_theme.json').write_text(json.dumps({'theme': 'Dark'}))
        settings = self.profile / 'settings.json'
        settings.write_text(json.dumps({'preferred_name': 'Sam'}))
        before = settings.read_text()
        with patch.object(migration, 'LEGACY_DATA_DIR', legacy), patch.object(migration, 'SETTINGS_FILE', settings), \
                patch.object(migration, 'CHATS_FILE', self.profile / 'chats.json'), \
                patch.object(migration, 'MODEL_DEFAULTS_FILE', self.profile / 'model_defaults.json'), \
                patch.object(migration, 'MODEL_ALIASES_FILE', self.profile / 'model_aliases.json'):
            migration.migrate_legacy_data()
        self.assertEqual(settings.read_text(), before)
        services = await self.container()
        self.assertEqual(services.settings['preferred_name'], 'Sam')


if __name__ == '__main__':
    unittest.main()
