"""Visible interactive browser profile, separate from Research and normal profiles.

Provider methods are internal primitives. An authorization gateway must mediate
each user operation. No cookie, credential, JavaScript or arbitrary selector API.
"""

import os
from pathlib import Path
import time
from urllib.parse import urlsplit
import uuid
from .privacy import secret_field
from .browser_semantics import accessible_name


def web_url(value):
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Interactive navigation requires an HTTP(S) URL without credentials")
    return value


def authentication_state(url, has_secret_field=False, labels=()):
    """Public sign-in signals only; no credential or cookie inspection."""
    parsed = urlsplit(url)
    if parsed.hostname == "accounts.google.com" or has_secret_field:
        return "LOGIN_REQUIRED"
    return "UNKNOWN"


class InteractiveBrowserProvider:
    name = "interactive_playwright"

    def __init__(self, profile_root, stop, timeout=15):
        self.profile = Path(profile_root) / "interactive-browser"
        self.stop = stop
        self.timeout = timeout
        self.driver = self.context = None
        self.pages = {}
        self.targets = {}
        self.target_signatures = {}
        self.dialog_pending = False
        self.action_guard = None
        self.attachments = {}
        from .browser_downloads import BrowserDownloads
        self.downloads = BrowserDownloads(self)

    def check(self):
        if self.stop.is_set():
            raise InterruptedError("Desktop control stopped")
        if self.dialog_pending:
            raise PermissionError("Browser dialog requires user review")

    async def launch(self, channel="chrome"):
        self.check()
        if channel not in {"chrome", "msedge"}:
            raise ValueError("Select installed Chrome or Edge; no browser download is automatic")
        if self.context:
            return await self.tabs()
        import importlib.util
        if importlib.util.find_spec("playwright") is None:
            from ..platform_support import PlatformUnavailable
            # The optional `browser` extra; packaged backends ship without it.
            raise PlatformUnavailable("Browser control needs the optional Playwright component, "
                                      "which is not part of this OLIVE build.")
        from playwright.async_api import async_playwright
        self.driver = await async_playwright().start()
        try:
            self.context = await self.driver.chromium.launch_persistent_context(str(self.profile),
                channel=channel, headless=False, chromium_sandbox=True, accept_downloads=True,
                downloads_path=str(self.downloads.directory),
                timeout=self.timeout * 1000,
                env={key: value for key, value in os.environ.items() if key.upper() in
                     {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH", "LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"}})
            self.context.set_default_timeout(self.timeout * 1000)
            self.context.on("page", self.register)
            for page in self.context.pages:
                self.register(page)
            return await self.tabs()
        except Exception:
            await self.close()
            raise

    def register(self, page):
        if page in self.pages.values():
            return
        self.pages[str(uuid.uuid4())] = page
        page.on("dialog", self.dialog)
        page.on("download", lambda download: self.downloads.receive(page, download))

    def dialog(self, dialog):
        self.dialog_pending = dialog  # Leave visible; never accept an unknown dialog.

    async def dialog_info(self):
        if self.stop.is_set():
            raise InterruptedError("Desktop control stopped")
        dialog = self.dialog_pending
        return {"pending": bool(dialog), "type": dialog.type if dialog else "",
                "message": dialog.message[:2000] if dialog else "", "untrusted_content": True}

    async def dismiss_dialog(self):
        if self.stop.is_set():
            raise InterruptedError("Desktop control stopped")
        dialog = self.dialog_pending
        if not dialog:
            raise ValueError("No browser dialog is pending")
        await dialog.dismiss()
        self.dialog_pending = False
        return {"dismissed": True}

    async def tabs(self):
        return [{"id": key, "url": page.url, "title": await page.title()}
                for key, page in self.pages.items() if not page.is_closed()]

    async def new_tab(self, url):
        self.check()
        if url != "about:blank":
            web_url(url)
        page = await self.context.new_page()
        self.register(page)
        await page.goto(url, wait_until="domcontentloaded")
        return await self.tabs()

    async def switch_tab(self, tab_id):
        self.check()
        await self.pages[tab_id].bring_to_front()
        return await self.observe(tab_id)

    async def close_tab(self, tab_id):
        self.check()
        if len([page for page in self.pages.values() if not page.is_closed()]) <= 1:
            raise ValueError("Keep one browser tab open, or close the browser explicitly")
        await self.pages[tab_id].close(run_before_unload=True)
        await self.clear_targets()
        return await self.tabs()

    async def navigate(self, tab_id, url):
        self.check()
        self.attachments.pop(tab_id, None)
        await self.pages[tab_id].goto(web_url(url), wait_until="domcontentloaded")
        return await self.observe(tab_id)

    async def clear_targets(self):
        targets, self.targets = self.targets, {}
        self.target_signatures.clear()
        for _, _, element, _ in targets.values():
            await element.dispose()

    async def signature(self, element):
        attributes = {key: await element.get_attribute(key) or "" for key in
                      ("aria-label", "placeholder", "type", "autocomplete", "role", "href", "formaction")}
        attributes["label"] = await accessible_name(element)
        return attributes

    async def observe(self, tab_id):
        self.check()
        page = self.pages[tab_id]
        await self.clear_targets()
        nodes = page.locator("button,input:not([type=password]),textarea,select,a,[role=button],[role=textbox],[role=tab],[role=status],[role=alert],h1,h2,h3")
        result = []
        for index in range(min(await nodes.count(), 150)):
            # Pin the observed DOM node. A live nth() locator would silently target
            # a different control if the page inserted or reordered elements.
            element = await nodes.nth(index).element_handle(timeout=500)
            if element is None:
                continue
            if not await element.is_visible():
                await element.dispose()
                continue
            input_type = await element.get_attribute("type") or ""
            autocomplete = await element.get_attribute("autocomplete") or ""
            if input_type == "password" or autocomplete in {"current-password", "new-password", "one-time-code"}:
                await element.dispose()
                continue
            name = await accessible_name(element)
            if secret_field(name, input_type, autocomplete):
                await element.dispose()
                continue
            target_id = str(uuid.uuid4())
            self.targets[target_id] = (tab_id, page.url, element, time.monotonic())
            self.target_signatures[target_id] = await self.signature(element)
            result.append({"id": target_id, "name": name, "type": input_type,
                           "tag": await element.evaluate("element => element.tagName.toLowerCase()"),
                           "role": await element.get_attribute("role") or "", "enabled": await element.is_enabled()})
        secret_present = await page.locator('input[type=password],input[autocomplete="current-password"],input[autocomplete="one-time-code"]').count() > 0
        auth = authentication_state(page.url, secret_present)
        public_url = urlsplit(page.url)._replace(query="", fragment="").geturl() if auth == "LOGIN_REQUIRED" else page.url
        return {"tab_id": tab_id, "url": public_url, "authentication_state": auth,
                "message": "Login required. Take over the visible browser to enter credentials manually." if auth == "LOGIN_REQUIRED" else "",
                "title": await page.title(), "controls": result,
                "untrusted_content": True}

    async def target(self, target_id):
        self.check()
        tab, url, element, observed = self.targets[target_id]
        if time.monotonic() - observed > 30 or self.pages[tab].url != url:
            raise ValueError("Browser target is stale; inspect again")
        if not await element.is_visible() or not await element.is_enabled():
            raise ValueError("Browser target changed")
        if await self.signature(element) != self.target_signatures[target_id]:
            raise ValueError("Browser target changed since observation; inspect again")
        if secret_field(await accessible_name(element),
                        await element.get_attribute("type"), await element.get_attribute("autocomplete")):
            raise PermissionError("Secret fields require manual user input")
        return tab, element

    async def field_value(self, target_id):
        _, element = await self.target(target_id)
        if await element.get_attribute("contenteditable") == "true":
            return (await element.inner_text())[:5001]
        return await element.input_value()

    async def attachment_names(self, tab_id):
        self.check()
        fields = self.pages[tab_id].locator("input[type=file]")
        if await fields.count() > 20:
            raise ValueError("Too many upload controls to review safely")
        names = []
        for index in range(await fields.count()):
            element = await fields.nth(index).element_handle(timeout=500)
            files = await element.get_property("files")
            properties = await files.get_properties()
            try:
                for key, file in properties.items():
                    if key.isdigit():
                        name = await file.get_property("name")
                        try:
                            names.append(await name.json_value())
                        finally:
                            await name.dispose()
                if len(names) > 20:
                    raise ValueError("Too many attachments to review safely")
            finally:
                for item in properties.values():
                    await item.dispose()
                await files.dispose()
                await element.dispose()
        if any(name not in names for name in self.attachments.get(tab_id, [])):
            raise ValueError("Previously selected attachments are no longer observable; review the draft manually")
        return names

    async def act(self, target_id, action, value=""):
        tab, element = await self.target(target_id)
        self.check()
        if self.action_guard:
            self.action_guard()
        if action == "click":
            await element.click(timeout=500)
        elif action == "fill":
            if not isinstance(value, str) or len(value) > 5000:
                raise ValueError("Invalid form text")
            await element.fill(value)
            if await self.field_value(target_id) != value:
                raise ValueError("Form text verification failed")
        elif action == "select":
            await element.select_option(value)
            if await element.input_value() != value:
                raise ValueError("Selection verification failed")
        elif action == "scroll":
            await element.scroll_into_view_if_needed(timeout=1000)
            # Fixed read-only geometry check; no model-supplied JavaScript.
            visible = await element.evaluate("e => { const r=e.getBoundingClientRect(); return r.bottom>0 && r.right>0 && r.top<innerHeight && r.left<innerWidth; }")
            if not visible:
                raise ValueError("Scroll target did not become visible in the viewport")
        else:
            raise ValueError("Unsupported interactive action")
        return await self.observe(tab)

    async def upload(self, target_id, name, mime_type, data):
        tab, element = await self.target(target_id)
        if await element.get_attribute("type") != "file" or len(data) > 10 * 1024 * 1024:
            raise ValueError("Invalid bounded upload")
        if self.action_guard:
            self.action_guard()
        await element.set_input_files({"name": name, "mimeType": mime_type, "buffer": data}, timeout=1000)
        if (await element.input_value()).replace("\\", "/").rsplit("/", 1)[-1] != name:
            raise ValueError("Attachment selection was not verified")
        self.attachments[tab] = [name]
        return {**await self.observe(tab), "verified": True, "attachment": name}

    async def close(self):
        if self.context:
            await self.context.close()
            self.context = None
        if self.driver:
            await self.driver.stop()
            self.driver = None
        self.pages.clear()
        self.targets.clear()
        self.target_signatures.clear()
        self.dialog_pending = False
