from pathlib import Path
import unittest
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from olive.desktop.shortcut_identity import matches_executable


class ShortcutIdentityTests(unittest.TestCase):
    def test_catalog_merges_only_shortcut_corroborated_running_identity(self):
        from olive.desktop.application_discovery import ApplicationDiscoveryService
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "Microsoft/Windows/Start Menu/Programs"
            folder.mkdir(parents=True)
            (folder / "Example.lnk").touch()
            resolver = SimpleNamespace(roaming_app_data=root, program_data=root / "other",
                _registered_app_paths=lambda: {}, _start_apps=lambda: [{"Name": "Example", "AppID": "example.desktop"}])
            windows = [{"application": "example", "executable": str(root / "Example.exe"), "package_identity": ""}]
            with patch("olive.tools.system.WindowsApplicationResolver", return_value=resolver), \
                 patch("olive.desktop.windows_observation.require_windows"), \
                 patch("olive.desktop.windows_observation.enumerate_windows", return_value=windows), \
                 patch("olive.desktop.shortcut_identity.shortcut_matches", return_value=True) as corroborate:
                values = ApplicationDiscoveryService.windows_catalog()
                self.assertEqual(len(values), 1)
                self.assertEqual(values[0].package_identity, "example.desktop")
                self.assertEqual(values[0].executable, windows[0]["executable"])
                corroborate.return_value = False
                self.assertEqual(len(ApplicationDiscoveryService.windows_catalog()), 2)

    def test_direct_shortcut_requires_exact_executable(self):
        self.assertTrue(matches_executable("apps/editor.exe", "", "apps/editor.exe"))
        self.assertFalse(matches_executable("apps/editor.exe", "", "other/editor.exe"))

    def test_squirrel_identity_requires_same_installation_and_named_child(self):
        target = Path("apps") / "Example" / "Update.exe"
        executable = target.parent / "app-1.0" / "Example.exe"
        self.assertTrue(matches_executable(target, "--processStart Example.exe", executable))
        self.assertFalse(matches_executable(target, "--processStart Different.exe", executable))
        self.assertFalse(matches_executable(target, "--processStart Example.exe --other", executable))
        self.assertFalse(matches_executable(target, "--processStart Example.exe", Path("elsewhere") / "app-1.0" / "Example.exe"))
