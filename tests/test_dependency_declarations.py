"""pyproject.toml is the canonical dependency declaration; requirements files mirror it.

Static checks only: nothing is installed, resolved or downloaded.
"""
from pathlib import Path
import re
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
# Pinned only for reproducible source installs; pulled in by vobject/python-dateutil.
TRANSITIVE_PINS = {'pytz', 'six'}
TEST_ONLY = {'aiosmtpd', 'atpublic', 'attrs'}
DEVELOPMENT_ONLY = {'pyside6', 'playwright'}
WINDOWS_ONLY = {'pywinauto', 'comtypes', 'pywin32', 'pywinpty', 'winrt-windows-media-control',
                'winrt-windows-media', 'winrt-windows-foundation', 'winrt-windows-foundation-collections'}


def name(requirement):
    return re.sub(r'[-_.]+', '-', re.match(r'[A-Za-z0-9._-]+', requirement).group()).lower()


def normal(requirement):
    return re.sub(r'\s+', '', requirement.replace('"', "'"))


def requirements(file):
    entries = []
    for line in (ROOT / file).read_text(encoding='utf-8').splitlines():
        line = line.split(' #')[0].strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('-r '):
            entries += requirements(line[3:].strip())
        else:
            entries.append(normal(line))
    return entries


class DependencyDeclarationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']
        cls.core = [normal(r) for r in project['dependencies']]
        cls.extras = {k: [normal(r) for r in v] for k, v in project['optional-dependencies'].items()}

    def test_development_environment_mirrors_core_and_dev_extras(self):
        declared = self.core + self.extras['qt'] + self.extras['browser']
        listed = [r for r in requirements('requirements.txt') if name(r) not in TRANSITIVE_PINS]
        self.assertEqual(sorted(listed), sorted(declared))
        self.assertEqual(len(listed), len(set(map(name, listed))), 'duplicate requirement')

    def test_transitive_pins_are_not_declared_runtime_dependencies(self):
        pinned = {name(r) for r in requirements('requirements-personal.txt')} & TRANSITIVE_PINS
        self.assertEqual(pinned, TRANSITIVE_PINS)
        self.assertFalse(TRANSITIVE_PINS & {name(r) for r in self.core})

    def test_studio_extra_mirrors_studio_requirements(self):
        self.assertEqual(sorted(requirements('requirements-studio.txt')), sorted(self.extras['studio']))

    def test_packaged_backend_excludes_qt_browser_and_test_only_packages(self):
        core = {name(r) for r in self.core}
        self.assertFalse(core & DEVELOPMENT_ONLY)
        everywhere = core | {name(r) for extra in self.extras.values() for r in extra}
        self.assertFalse(everywhere & TEST_ONLY)
        self.assertEqual({name(r) for r in requirements('requirements-mail-test.txt')} - {'cryptography'}, TEST_ONLY)

    def test_platform_packages_stay_conditional(self):
        for entry in self.core + [r for extra in self.extras.values() for r in extra]:
            if name(entry) in WINDOWS_ONLY:
                self.assertIn(";sys_platform=='win32'", entry)
            elif name(entry) == 'secretstorage':
                self.assertIn(";sys_platform=='linux'", entry)
            elif name(entry) == 'keyring':
                self.assertIn(";sys_platform=='darwin'", entry)
            else:
                self.assertNotIn('sys_platform', entry, entry)

    def test_windows_backend_carries_pywinpty_and_other_targets_do_not(self):
        self.assertIn("pywinpty==3.0.5;sys_platform=='win32'", self.core)
        self.assertNotIn('pywinpty', {name(r) for r in self.extras['studio']})
        locks = ROOT / 'packaging/backend/locks'
        windows = (locks / 'windows-x86_64.txt').read_text(encoding='utf-8')
        self.assertIn('pywinpty==3.0.5 \\', windows)
        # The CPython 3.14 win_amd64 wheel the Windows artefact installs (PyPI digest).
        self.assertIn('03bb3c16d691d9242267201830bcd0e64a9b663170e9042bc84b210da9de15ac', windows)
        for target in ('linux-x86_64', 'macos-arm64'):
            self.assertNotIn('pywinpty', (locks / f'{target}.txt').read_text(encoding='utf-8'))
            self.assertNotIn('playwright', (locks / f'{target}.txt').read_text(encoding='utf-8'))
        self.assertNotIn('playwright', windows)

    def test_backend_locks_cover_every_core_dependency_for_their_platform(self):
        platforms = {'linux-x86_64': 'linux', 'windows-x86_64': 'win32', 'macos-arm64': 'darwin'}
        for target, platform in platforms.items():
            text = (ROOT / f'packaging/backend/locks/{target}.txt').read_text(encoding='utf-8')
            locked = {name(line) for line in text.splitlines() if re.match(r'[A-Za-z0-9]', line)}
            wanted = {name(r) for r in self.core
                      if ';sys_platform' not in r or r.endswith(f";sys_platform=='{platform}'")}
            self.assertEqual(wanted - locked, set(), target)
            self.assertFalse(locked & (DEVELOPMENT_ONLY | TEST_ONLY), target)

    def test_connect_ci_installs_the_backend_lock_not_a_hand_kept_subset(self):
        workflow = (ROOT / '.github/workflows/connect-portable.yml').read_text(encoding='utf-8')
        installs = [line.rstrip().rstrip("'") for line in workflow.splitlines() if 'pip install' in line]
        self.assertEqual(len(installs), 1, installs)
        self.assertIn('--require-hashes', installs[0])
        self.assertIn('--no-deps', installs[0])
        self.assertTrue(installs[0].endswith(' -r packaging/backend/locks/${{ matrix.lock }}.txt'), installs[0])
        matrix = dict(re.findall(r'\{ os: ([\w-]+), lock: ([\w-]+) \}', workflow))
        self.assertEqual(matrix, {'ubuntu-latest': 'linux-x86_64', 'windows-latest': 'windows-x86_64'})


if __name__ == '__main__':
    unittest.main()
