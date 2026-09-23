"""Owner installer mutates only the named entry, including without Flatpak."""
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class ProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.receipt = Path(self.temp.name) / 'receipt.json'
        self.entries = {'': ['yes'], 'org.example.Other': ['yes']}
        self.app_id = 'local.dmdo.desktop'
        self.bus = Mock()
        self.bus.get_unique_name.return_value = ':1.42'
        def call(store, path, interface, method, variant, *_):
            signature, args = variant
            if method == 'SetPermission':
                self.assertEqual(signature, '(sbssas)')
                table, create, entry, app, permissions = args
                self.assertEqual((table, create, entry, app), ('kde-authorized', True, 'remote-desktop', self.app_id))
                self.entries[app] = permissions
            elif method == 'DeletePermission':
                self.assertEqual(args, ('kde-authorized', 'remote-desktop', self.app_id))
                del self.entries[args[2]]
            else:
                self.fail(method)
        self.bus.call_sync.side_effect = call
        portal = SimpleNamespace(bus=self.bus, close=Mock())
        native = SimpleNamespace(Portal=Mock(return_value=portal), Gio=Mock(), GLib=SimpleNamespace(Variant=lambda sig, value: (sig, value)))
        spec = importlib.util.spec_from_file_location('isolated_kde_setup', Path(__file__).resolve().parents[1] / 'scripts/provision_olive_kde.py')
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules', {'olive.desktop.linux.portal': native}):
            spec.loader.exec_module(self.module)
        self.module.lookup = lambda bus, app: self.entries.get(app)
        self.patches = [patch.dict('sys.modules', {'install_linux_desktop_entry': SimpleNamespace(install=Mock())}),
                        patch.object(self.module.shutil, 'which', return_value=None)]
        for p in self.patches:
            p.start(); self.addCleanup(p.stop)

    def test_session_bus_fallback_and_exact_absent_entry_rollback(self):
        before = dict(self.entries)
        result = self.module.provision(self.receipt)
        self.assertEqual(result['transport'], 'PermissionStore')
        self.assertEqual(self.entries[self.app_id], ['yes'])
        self.assertEqual(self.receipt.stat().st_mode & 0o777, 0o600)
        self.module.Portal.assert_called_once()
        self.module.provision(self.receipt, restore=True)
        self.assertEqual(self.entries, before)

    def test_existing_permission_is_restored_without_touching_other_grants(self):
        self.entries[self.app_id] = ['no']
        before = dict(self.entries)
        self.module.provision(self.receipt)
        self.module.provision(self.receipt, restore=True)
        self.assertEqual(self.entries, before)

    def test_repeated_setup_or_changed_permission_does_not_regrant(self):
        self.module.provision(self.receipt)
        self.entries[self.app_id] = ['no']
        calls = self.bus.call_sync.call_count
        with self.assertRaises(FileExistsError):
            self.module.provision(self.receipt)
        with self.assertRaises(ValueError):
            self.module.provision(self.receipt, restore=True)
        self.assertEqual(self.bus.call_sync.call_count, calls)

    def test_failed_identity_registration_cannot_write_or_create_receipt(self):
        self.module.Portal.side_effect = RuntimeError('Registry unavailable')
        with self.assertRaises(RuntimeError):
            self.module.provision(self.receipt)
        self.assertFalse(self.receipt.exists())
        self.bus.call_sync.assert_not_called()
