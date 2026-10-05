"""Playwright is optional: Core never needs it, HTTP research works without it, no browser is downloaded."""
import asyncio
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock

from olive.research import browser as research_browser
from olive.research.browser import BrowserService, NO_BROWSER, PlaywrightBrowserProvider, UNAVAILABLE, system_browser
from olive.research.extraction import extract_page

ROOT = Path(__file__).resolve().parents[1]


class OptionalPlaywrightTests(unittest.TestCase):
    def test_core_backend_never_depends_on_playwright(self):
        project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']
        self.assertFalse([d for d in project['dependencies'] if d.lower().startswith('playwright')])
        for target in ('linux-x86_64', 'windows-x86_64', 'macos-arm64'):
            lock = (ROOT / f'packaging/backend/locks/{target}.txt').read_text(encoding='utf-8')
            self.assertNotIn('playwright==', lock)

    def test_absent_component_is_reported_truthfully(self):
        with mock.patch.object(PlaywrightBrowserProvider, 'installed', staticmethod(lambda: False)):
            availability = PlaywrightBrowserProvider.availability()
        self.assertFalse(availability['installed'])
        self.assertEqual(availability['setup'], UNAVAILABLE)
        self.assertIn('optional', UNAVAILABLE)
        with mock.patch.object(PlaywrightBrowserProvider, 'installed', staticmethod(lambda: False)):
            with self.assertRaises(RuntimeError) as caught:
                asyncio.run(PlaywrightBrowserProvider().ensure_started())
        self.assertIn('optional OLIVE component', str(caught.exception))

    def test_http_research_works_without_playwright(self):
        service = BrowserService('auto')
        page = extract_page('<html><title>t</title><body><p>short</p></body></html>', 'https://example.com/')

        async def http_open(url):
            return page
        service.http.open = http_open
        with mock.patch.object(PlaywrightBrowserProvider, 'installed', staticmethod(lambda: False)):
            self.assertIs(asyncio.run(service.open('https://example.com/')), page)

    def test_auto_keeps_the_http_page_when_no_system_browser_exists(self):
        service = BrowserService('auto')
        page = extract_page('<html><body>x</body></html>', 'https://example.com/')

        async def http_open(url):
            return page

        async def rendered_open(url):
            raise AssertionError('must not launch without a system browser')
        service.http.open = http_open
        service.rendered.open = rendered_open
        with mock.patch.object(PlaywrightBrowserProvider, 'installed', staticmethod(lambda: True)), \
                mock.patch.object(research_browser, 'system_browser', return_value=None):
            self.assertIs(asyncio.run(service.open('https://example.com/')), page)

    def test_never_downloads_a_browser(self):
        with mock.patch.object(PlaywrightBrowserProvider, 'installed', staticmethod(lambda: True)), \
                mock.patch.object(research_browser, 'system_browser', return_value=None):
            with self.assertRaises(RuntimeError) as caught:
                asyncio.run(PlaywrightBrowserProvider().ensure_started())
        self.assertEqual(str(caught.exception), NO_BROWSER)
        source = (ROOT / 'olive/research/browser.py').read_text(encoding='utf-8')
        self.assertNotIn('playwright install', source)

    def test_system_browser_detection_prefers_installed_browsers(self):
        with tempfile.TemporaryDirectory() as directory:
            edge = Path(directory) / 'Microsoft/Edge/Application/msedge.exe'
            edge.parent.mkdir(parents=True)
            edge.write_text('')
            self.assertEqual(system_browser('win32', {'PROGRAMFILES': directory}), {'channel': 'msedge'})
            self.assertIsNone(system_browser('win32', {'PROGRAMFILES': str(Path(directory) / 'none')}))
        with mock.patch.object(research_browser.Path, 'is_file', return_value=False):
            self.assertEqual(system_browser('linux', {}, which=lambda n: '/usr/bin/chromium' if n == 'chromium' else None),
                             {'executable_path': '/usr/bin/chromium'})
            self.assertIsNone(system_browser('linux', {}, which=lambda n: None))


if __name__ == '__main__':
    unittest.main()
