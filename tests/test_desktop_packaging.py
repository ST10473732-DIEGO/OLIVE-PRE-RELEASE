"""Desktop package identity and contents: Linux entries, electron-builder targets, backend inputs."""
import json
from pathlib import Path
import re
import tempfile
import unittest

from olive.services import linux_desktop_entries as entries

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = json.loads((ROOT / 'desktop/package.json').read_text(encoding='utf-8'))
BUILD = PACKAGE['build']
RUNTIME = json.loads((ROOT / 'packaging/backend/python-runtime.json').read_text(encoding='utf-8'))


def parse(text):
    lines = text.splitlines()
    assert lines[0] == '[Desktop Entry]'
    return dict(line.split('=', 1) for line in lines[1:] if line)


class LinuxDesktopEntryTests(unittest.TestCase):
    def test_templates_match_the_renderers(self):
        self.assertEqual((ROOT / 'packaging/linux/olive.desktop.in').read_text(encoding='utf-8'), entries.visible_entry())
        self.assertEqual((ROOT / 'packaging/linux/local.dmdo.desktop.desktop.in').read_text(encoding='utf-8'),
                         entries.compatibility_entry())

    def test_visible_entry_is_the_one_olive_menu_item(self):
        visible = parse(entries.visible_entry())
        self.assertEqual((visible['Name'], visible['Icon'], visible['StartupWMClass'], visible['Exec']),
                         ('OLIVE', 'olive', 'olive', '@EXEC@'))
        self.assertNotIn('NoDisplay', visible)
        hidden = parse(entries.compatibility_entry())
        self.assertEqual(hidden['NoDisplay'], 'true')  # Never a second menu entry.
        self.assertNotIn('StartupWMClass', hidden)  # Windows group under olive.desktop only.
        self.assertEqual(entries.compatibility_name(), 'local.dmdo.desktop.desktop')

    def test_install_writes_both_and_never_replaces_a_user_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            launcher = Path(directory) / 'My Apps' / 'OLIVE-1.0.0.AppImage'
            result = entries.install(str(launcher), directory)
            self.assertEqual(result, {'olive.desktop': 'written', 'local.dmdo.desktop.desktop': 'written'})
            body = (Path(directory) / 'applications/olive.desktop').read_text()
            self.assertIn('Exec="' + str(launcher) + '"', body)
            self.assertEqual(entries.install(str(launcher), directory)['olive.desktop'], 'unchanged')
            user = Path(directory) / 'applications/olive.desktop'
            user.write_text('[Desktop Entry]\nName=OLIVE\nExec=/home/u/.local/bin/olive\n')
            self.assertEqual(entries.install(str(launcher), directory)['olive.desktop'], 'kept-user-entry')
            self.assertIn('/home/u/.local/bin/olive', user.read_text())
            with self.assertRaisesRegex(ValueError, 'mount'):
                entries.install('/tmp/.mount_OLIVExy/olive', directory)

    def test_portal_identity_is_only_added_by_packaged_builds(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(entries.ensure_portal_identity({'OLIVE_APP_EXECUTABLE': '/a/OLIVE.AppImage',
                                                              'XDG_DATA_HOME': directory}))
            self.assertFalse((Path(directory) / 'applications').exists())

    def test_electron_announces_the_same_desktop_identity(self):
        main = (ROOT / 'desktop/electron/main/index.ts').read_text(encoding='utf-8')
        self.assertIn('app.setDesktopName("olive.desktop")', main)
        self.assertEqual(PACKAGE['desktopName'], 'olive.desktop')
        linux = BUILD['linux']
        self.assertEqual(BUILD['executableName'], 'olive')
        self.assertTrue(linux['syncDesktopName'])
        self.assertEqual(linux['desktop']['entry']['StartupWMClass'], 'olive')
        self.assertEqual(linux['desktop']['entry']['Icon'], 'olive')
        self.assertEqual(linux['desktop']['entry']['Name'], 'OLIVE')


class ElectronBuilderTargetTests(unittest.TestCase):
    def test_stable_upgrade_identity_and_product(self):
        self.assertEqual(BUILD['appId'], json.loads((ROOT / 'olive/identity.json').read_text())['app_id'])
        self.assertEqual(BUILD['appId'], 'local.dmdo.desktop')
        self.assertEqual(BUILD['productName'], 'OLIVE')
        self.assertEqual(BUILD['beforePack'], 'scripts/require-backend.cjs')

    def test_linux_appimage(self):
        self.assertEqual(BUILD['linux']['target'], [{'target': 'AppImage', 'arch': ['x64']}])
        self.assertEqual(BUILD['linux']['artifactName'], 'OLIVE-${version}.${ext}')

    def test_windows_per_user_nsis_never_deletes_data(self):
        nsis = BUILD['nsis']
        self.assertEqual(BUILD['win']['target'], [{'target': 'nsis', 'arch': ['x64']}])
        self.assertEqual(nsis['artifactName'], 'OLIVE-Setup-${version}.${ext}')
        self.assertFalse(nsis['perMachine'])
        self.assertFalse(nsis['allowElevation'])
        self.assertFalse(nsis['deleteAppDataOnUninstall'])
        # A chosen directory could be the data root; the uninstaller removes $INSTDIR recursively.
        self.assertFalse(nsis['allowToChangeInstallationDirectory'])
        self.assertTrue(nsis['createStartMenuShortcut'])
        self.assertFalse(nsis['createDesktopShortcut'])  # Optional: asked by installer.nsh.
        script = (ROOT / 'desktop' / nsis['include']).resolve().read_text(encoding='utf-8')
        self.assertIn('MessageBox MB_YESNO', script)
        # Fresh installs go to Programs\OLIVE, not the package name; an existing install stays put.
        self.assertEqual(BUILD['productName'], 'OLIVE')
        pre_init = re.search(r'(?ms)^!macro preInit\n(.*?)^!macroend', script).group(1)
        self.assertIn('!ifndef BUILD_UNINSTALLER', pre_init)
        self.assertIn('ReadRegStr $0 HKCU "${INSTALL_REGISTRY_KEY}" InstallLocation', pre_init)
        self.assertIn('${if} $0 == ""', pre_init)
        self.assertIn('WriteRegStr HKCU "${INSTALL_REGISTRY_KEY}" InstallLocation "$0\\${PRODUCT_NAME}"', pre_init)
        self.assertNotIn('HKLM', pre_init)
        self.assertNotIn('${PRODUCT_FILENAME}', pre_init)  # That follows executableName: Programs\olive.
        self.assertNotRegex(script, r'RMDir[^\n]*(LOCALAPPDATA|PROFILE|\.olive|APPDATA)')
        self.assertNotIn('cscLink', json.dumps(BUILD))  # No signing certificate is assumed.

    def test_macos_dmg_is_unsigned_with_hardened_runtime_placeholders(self):
        mac = BUILD['mac']
        self.assertEqual(mac['target'], [{'target': 'dmg', 'arch': ['arm64']}])
        self.assertIsNone(mac['identity'])
        self.assertFalse(mac['notarize'])
        self.assertTrue(mac['hardenedRuntime'])
        for key in ('entitlements', 'entitlementsInherit', 'icon'):
            self.assertTrue((ROOT / 'desktop' / mac[key]).resolve().is_file(), key)
        icns = (ROOT / 'assets/branding/olive.icns').read_bytes()
        self.assertEqual(icns[:4], b'icns')

    def test_package_contents_are_built_output_backend_icons_and_notices_only(self):
        # Main and renderer are fully bundled by Vite; no node_modules tree enters app.asar.
        self.assertEqual(BUILD['files'], ['out/electron/**/*', 'out/renderer/**/*', 'package.json', '!node_modules{,/**/*}'])
        self.assertFalse(BUILD['npmRebuild'])
        self.assertEqual(BUILD['appImage']['executableArgs'], [])  # The desktop entry never forces --no-sandbox.
        resources = {item['from']: item['to'] for item in BUILD['extraResources']}
        self.assertEqual(resources['backend-artifact'], 'backend')
        self.assertEqual(resources['../LICENSE'], 'legal/LICENSE.txt')
        self.assertEqual(resources['../THIRD_PARTY_NOTICES.md'], 'legal/THIRD_PARTY_NOTICES.md')
        # Generated per build by packaging/legal/collect_notices.py (PASS 2C).
        self.assertEqual(resources['backend-artifact/THIRD_PARTY-backend.txt'], 'legal/THIRD_PARTY-backend.txt')
        # PASS 2D: npm licence texts (generated by npm run build) and the Electron/Chromium notices.
        self.assertEqual(resources['out/legal/THIRD_PARTY-npm.txt'], 'legal/THIRD_PARTY-npm.txt')
        self.assertEqual(resources['node_modules/electron/dist/LICENSE'], 'legal/LICENSE.electron.txt')
        self.assertEqual(resources['node_modules/electron/dist/LICENSES.chromium.html'], 'legal/LICENSES.chromium.html')
        self.assertEqual(set(resources) - {'backend-artifact', '../assets/branding/olive.ico', '../assets/branding/olive-256.png',
                                           '../LICENSE', '../THIRD_PARTY_NOTICES.md', 'THIRD_PARTY.md',
                                           'backend-artifact/THIRD_PARTY-backend.txt', 'out/legal/THIRD_PARTY-npm.txt',
                                           'node_modules/electron/dist/LICENSE',
                                           'node_modules/electron/dist/LICENSES.chromium.html'}, set())
        self.assertEqual(BUILD['directories']['output'], 'dist')  # Never inside out/, which is packaged.


class BackendArtifactInputTests(unittest.TestCase):
    def test_python_runtime_is_pinned_with_published_checksums(self):
        self.assertEqual(RUNTIME['distribution'], 'python-build-standalone')
        for target, spec in RUNTIME['targets'].items():
            self.assertRegex(spec['sha256'], r'^[0-9a-f]{64}$')
            self.assertIn(RUNTIME['release'], spec['url'])
            self.assertIn(RUNTIME['version'], spec['asset'])
            self.assertTrue(spec['url'].startswith('https://github.com/astral-sh/python-build-standalone/releases/download/'))
            self.assertTrue((ROOT / 'packaging/backend' / spec['lock']).is_file(), target)
        self.assertEqual(set(RUNTIME['targets']), {'linux-x86_64', 'windows-x86_64', 'macos-arm64'})

    def test_locks_are_hashed_core_only_and_platform_correct(self):
        def names(target):
            text = (ROOT / 'packaging/backend' / RUNTIME['targets'][target]['lock']).read_text()
            pins = re.findall(r'^([A-Za-z0-9._-]+)==\S+ \\$', text, re.M)
            self.assertEqual(text.count('==') , len(pins))
            self.assertGreaterEqual(text.count('--hash=sha256:'), len(pins))
            return {p.lower() for p in pins}
        linux, windows, mac = names('linux-x86_64'), names('windows-x86_64'), names('macos-arm64')
        for found in (linux, windows, mac):
            self.assertFalse(found & {'pyside6', 'shiboken6', 'playwright', 'pip', 'debugpy', 'python-lsp-server'})
            self.assertIn('cryptography', found)
        self.assertIn('secretstorage', linux)
        self.assertNotIn('secretstorage', mac | windows)
        self.assertIn('keyring', mac)
        self.assertNotIn('keyring', linux | windows)
        self.assertIn('pywin32', windows)

    def test_build_excludes_qt_and_dmdo(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('build_backend', ROOT / 'packaging/backend/build_backend.py')
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        sources = [p.as_posix() for p in build.olive_sources()]
        self.assertTrue(sources)
        self.assertFalse([s for s in sources if s.startswith('olive/ui_qt/') or s == 'olive/__main__.py'])
        self.assertFalse([s for s in sources if not s.startswith('olive/') or '__pycache__' in s])
        self.assertIn('olive/runtime_manifest/1.0.0.json', sources)
        self.assertIn('pip', build.FORBIDDEN_DISTRIBUTIONS)

    @unittest.skipUnless((ROOT / 'desktop/backend-artifact/olive-backend.json').is_file(), 'no locally built backend artefact')
    def test_built_artefact_manifest(self):
        manifest = json.loads((ROOT / 'desktop/backend-artifact/olive-backend.json').read_text())
        self.assertEqual(manifest['schema'], 'olive-backend/1')
        self.assertEqual(manifest['version'], json.loads((ROOT / 'olive/identity.json').read_text())['version'])
        self.assertEqual(manifest['python']['sha256'], RUNTIME['targets'][manifest['target']]['sha256'])
        names = {d['name'].lower() for d in manifest['dependencies']['distributions']}
        self.assertFalse(names & {'pyside6', 'playwright', 'pip'})
        self.assertFalse((ROOT / 'desktop/backend-artifact/olive/ui_qt').exists())
        self.assertFalse((ROOT / 'desktop/backend-artifact/dmdo').exists())


class ApplicationIconTests(unittest.TestCase):
    """OLIVE 2: the dark icon on every desktop, light and dark appearances on iOS."""
    ARTWORK = ROOT / 'assets/branding/olive2/app-icons'
    APPICONSET = ROOT / 'mobile/ios/OLIVEMobile/Assets.xcassets/AppIcon.appiconset'

    def test_desktop_packaging_uses_the_canonical_icons(self):
        self.assertEqual(BUILD['win']['icon'], '../assets/branding/olive.ico')
        self.assertEqual(BUILD['nsis']['installerIcon'], '../assets/branding/olive.ico')
        self.assertEqual(BUILD['nsis']['uninstallerIcon'], '../assets/branding/olive.ico')
        self.assertEqual(BUILD['mac']['icon'], '../assets/branding/olive.icns')
        self.assertEqual(BUILD['linux']['icon'], '../assets/branding/olive-512.png')

    def test_installed_icons_match_the_supplied_artwork(self):
        import subprocess
        import sys
        result = subprocess.run([sys.executable, str(ROOT / 'packaging/icons/make_icons.py'), '--check'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_windows_and_macos_icons_carry_every_size(self):
        from PIL import Image
        with Image.open(ROOT / 'assets/branding/olive.ico') as ico:
            self.assertTrue({16, 24, 32, 48, 64, 128, 256} <= {w for w, _ in ico.info['sizes']})
        with Image.open(ROOT / 'assets/branding/olive.icns') as icns:
            self.assertTrue({(16, 16, 2), (128, 128, 1), (256, 256, 2), (512, 512, 2)} <= set(icns.info['sizes']))

    def test_ios_icon_has_light_default_and_dark_appearance_both_opaque(self):
        from PIL import Image
        catalog = json.loads((self.APPICONSET / 'Contents.json').read_text(encoding='utf-8'))
        appearances = {tuple((a['appearance'], a['value']) for a in image.get('appearances', [])): image
                       for image in catalog['images']}
        self.assertEqual(set(appearances), {(), (('luminosity', 'dark'),)})
        self.assertEqual(appearances[()]['filename'], 'AppIcon-Light.png')
        self.assertEqual(appearances[(('luminosity', 'dark'),)]['filename'], 'AppIcon-Dark.png')
        for image in catalog['images']:
            self.assertEqual((image['idiom'], image['platform'], image['size']), ('universal', 'ios', '1024x1024'))
            with Image.open(self.APPICONSET / image['filename']) as icon:
                self.assertEqual(icon.size, (1024, 1024))
                self.assertEqual(icon.mode, 'RGB')  # No alpha channel: App Store rejects transparent icons.
                self.assertNotIn('transparency', icon.info)
        self.assertEqual(sorted(p.name for p in self.APPICONSET.iterdir()),
                         ['AppIcon-Dark.png', 'AppIcon-Light.png', 'Contents.json'])
        pbxproj = (ROOT / 'mobile/ios/OLIVEMobile.xcodeproj/project.pbxproj').read_text(encoding='utf-8')
        self.assertIn('ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon;', pbxproj)


if __name__ == '__main__':
    unittest.main()
