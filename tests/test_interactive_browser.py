import unittest
import time
from unittest.mock import AsyncMock, Mock
from olive.desktop.interactive_browser import web_url, InteractiveBrowserProvider
from olive.desktop.emergency_stop import EmergencyStop


class InteractiveBrowserTests(unittest.IsolatedAsyncioTestCase):
    def test_authentication_requires_user_takeover_without_claiming_login(self):
        from olive.desktop.interactive_browser import authentication_state
        self.assertEqual(authentication_state("https://accounts.google.com/signin?state=opaque"), "LOGIN_REQUIRED")
        self.assertEqual(authentication_state("https://example.test/login", True), "LOGIN_REQUIRED")
        self.assertEqual(authentication_state("https://mail.google.com/mail/"), "UNKNOWN")
        self.assertEqual(authentication_state("https://accounts.google.com.attacker.test/"), "UNKNOWN")

    def test_only_web_navigation_without_credentials(self):
        for url in ("file:///secret", "javascript:alert(1)", "https://user:password@example.test", "data:text/html,test"):
            with self.assertRaises(ValueError):
                web_url(url)
        self.assertEqual(web_url("http://127.0.0.1:8000"), "http://127.0.0.1:8000")

    async def test_stop_prevents_browser_launch(self):
        stop = EmergencyStop()
        stop.set()
        browser = InteractiveBrowserProvider("unused", stop)
        with self.assertRaises(InterruptedError):
            await browser.launch()
        self.assertIsNone(browser.driver)

    async def test_unknown_browser_never_downloads_runtime(self):
        browser = InteractiveBrowserProvider("unused", EmergencyStop())
        with self.assertRaises(ValueError):
            await browser.launch("download-chromium")

    def test_no_arbitrary_browser_execution_contract(self):
        self.assertFalse(hasattr(InteractiveBrowserProvider, "evaluate"))
        self.assertFalse(hasattr(InteractiveBrowserProvider, "cookies"))

    async def test_modal_blocks_actions_until_explicit_dismissal(self):
        browser = InteractiveBrowserProvider("unused", EmergencyStop())
        dialog = Mock(type="confirm", message="Untrusted page request", dismiss=AsyncMock())
        browser.dialog(dialog)
        with self.assertRaises(PermissionError):
            browser.check()
        info = await browser.dialog_info()
        self.assertTrue(info["untrusted_content"])
        await browser.dismiss_dialog()
        dialog.dismiss.assert_awaited_once()
        browser.check()
        dialog.accept.assert_not_called()

    def target_fixture(self):
        browser = InteractiveBrowserProvider("unused", EmergencyStop())
        element = Mock()
        attributes = {"aria-label": "Preview"}
        element.get_attribute = AsyncMock(side_effect=lambda key: attributes.get(key))
        element.inner_text = AsyncMock(return_value="Preview")
        element.evaluate = AsyncMock(side_effect=lambda script: attributes.get("aria-label", "Preview"))
        element.is_visible = AsyncMock(return_value=True)
        element.is_enabled = AsyncMock(return_value=True)
        element.click = AsyncMock()
        element.dispose = AsyncMock()
        browser.pages["tab"] = Mock(url="https://example.test")
        browser.targets["target"] = ("tab", "https://example.test", element, time.monotonic())
        return browser, element, attributes

    async def test_changed_semantic_target_cannot_use_previous_approval(self):
        browser, element, attributes = self.target_fixture()
        browser.target_signatures["target"] = await browser.signature(element)
        attributes["aria-label"] = "Send"
        with self.assertRaisesRegex(ValueError, "changed since observation"):
            await browser.act("target", "click")
        element.click.assert_not_awaited()

    async def test_navigation_invalidates_observed_target(self):
        browser, element, _ = self.target_fixture()
        browser.pages["tab"].url = "https://different.test"
        with self.assertRaisesRegex(ValueError, "stale"):
            await browser.act("target", "click")
        element.click.assert_not_awaited()

    async def test_removed_dom_node_never_retargets_neighbor(self):
        browser, element, _ = self.target_fixture()
        element.is_visible.return_value = False
        with self.assertRaisesRegex(ValueError, "target changed"):
            await browser.act("target", "click")
        element.click.assert_not_awaited()

    async def test_stop_blocks_already_observed_target(self):
        browser, element, _ = self.target_fixture()
        browser.stop.set()
        with self.assertRaises(InterruptedError):
            await browser.act("target", "click")
        element.click.assert_not_awaited()

    async def test_refresh_releases_pinned_nodes(self):
        browser, element, _ = self.target_fixture()
        await browser.clear_targets()
        element.dispose.assert_awaited_once()
        self.assertFalse(browser.targets)

    async def test_last_moment_focus_loss_blocks_browser_input(self):
        browser, element, _ = self.target_fixture()
        browser.target_signatures["target"] = await browser.signature(element)
        browser.action_guard = Mock(side_effect=PermissionError("Focus changed"))
        with self.assertRaisesRegex(PermissionError, "Focus changed"):
            await browser.act("target", "click")
        element.click.assert_not_awaited()
