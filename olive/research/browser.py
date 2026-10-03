"""Browser observations are data only. No arbitrary browser evaluation API."""

import asyncio
import os
from pathlib import Path
from .extraction import extract_page, MAX_HTML
from .http import fetch
from .urls import normalize_url
from .browser_proxy import PublicBrowserProxy


class ObservationBrowser:
    def __init__(self, timeout=25):
        self.timeout = timeout
        self.observations = {}

    def remember(self, page):
        self.observations[page.url] = page
        while len(self.observations) > 32:
            self.observations.pop(next(iter(self.observations)))
        return page

    async def navigate(self, url):
        return await self.open(url)

    async def read(self, url):
        return self.observations.get(normalize_url(url)) or await self.open(url)

    async def page_info(self, url):
        value = (await self.read(url)).to_dict()
        value.pop("text")
        return value

    async def links(self, url):
        return (await self.read(url)).links

    async def follow_link(self, url, target):
        normalized = normalize_url(target, url)
        if normalized not in {link["url"] for link in await self.links(url)}:
            raise ValueError("Link was not present in the observed page")
        return await self.open(normalized)

    async def cancel(self):
        return None

    async def close(self):
        self.observations.clear()


class HTTPBrowserProvider(ObservationBrowser):
    name = "http"

    async def open(self, url):
        url, kind, body = await fetch(url, timeout=self.timeout)
        if not any(
            mime in kind for mime in ("text/html", "application/xhtml+xml", "text/plain", "text/markdown")
        ):
            raise ValueError("This source is a download; use the explicit quarantine/import workflow")
        return self.remember(extract_page(body.decode("utf-8", errors="replace"), url, kind))


UNAVAILABLE = ("The browser research provider (Playwright) is not part of this OLIVE build. "
               "Research uses HTTP pages; choose Auto or HTTP in Research settings.")


class PlaywrightBrowserProvider(ObservationBrowser):
    name = "playwright"

    def __init__(self, timeout=25):
        super().__init__(timeout)
        self.driver = self.browser = self.proxy = None
        self.lock = asyncio.Lock()
        self.contexts = set()

    @staticmethod
    def installed():
        """Playwright is an optional extra; packaged backends do not include it."""
        import importlib.util

        return importlib.util.find_spec("playwright") is not None

    @staticmethod
    def availability():
        edge = any(
            (Path(os.environ.get(key, "")) / "Microsoft/Edge/Application/msedge.exe").is_file()
            for key in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")
        )
        if not PlaywrightBrowserProvider.installed():
            return {"driver": False, "installed_edge": edge, "installed": False, "setup": UNAVAILABLE}
        from playwright._impl._driver import compute_driver_executable

        driver, _ = compute_driver_executable()
        return {
            "driver": Path(driver).is_file(),
            "installed_edge": edge,
            "installed": True,
            "setup": "If Chromium/Edge is unavailable, run: python -m playwright install chromium",
        }

    async def ensure_started(self):
        async with self.lock:
            if self.browser:
                return
            if not self.installed():
                raise RuntimeError(UNAVAILABLE)
            from playwright.async_api import async_playwright

            self.driver = await async_playwright().start()
            self.proxy = PublicBrowserProxy()
            endpoint = await self.proxy.start()
            # No inherited API credentials, cookies or user browser profile.
            environment = {
                k: v
                for k, v in os.environ.items()
                if k.upper()
                in {
                    "SYSTEMROOT",
                    "WINDIR",
                    "TEMP",
                    "TMP",
                    "PATH",
                    "PROGRAMFILES",
                    "PROGRAMFILES(X86)",
                    "LOCALAPPDATA",
                }
            }
            try:
                self.browser = await self.driver.chromium.launch(
                    channel="msedge" if self.availability()["installed_edge"] else None,
                    headless=True,
                    chromium_sandbox=True,
                    env=environment,
                    proxy={"server": endpoint, "bypass": "<-loopback>"},
                    args=["--disable-quic", "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"],
                )
            except Exception as error:
                await self.proxy.close()
                await self.driver.stop()
                self.proxy = self.driver = None
                raise RuntimeError(
                    "Research browser unavailable. Install Chromium manually with: python -m playwright install chromium"
                ) from error

    async def open(self, url):
        url = normalize_url(url)
        await self.ensure_started()
        context = await self.browser.new_context(
            accept_downloads=False, service_workers="block", permissions=[], ignore_https_errors=False
        )
        self.contexts.add(context)

        async def route(request_route):
            request = request_route.request
            try:
                normalize_url(request.url)
                if request.method not in {"GET", "HEAD"} or request.resource_type in {
                    "media",
                    "font",
                    "image",
                    "websocket",
                }:
                    raise ValueError("Resource not required for page reading")
            except ValueError:
                await request_route.abort()
            else:
                await request_route.continue_()

        try:
            await context.route("**/*", route)
            await context.route_web_socket("**/*", lambda ws: ws.close())
            page = await context.new_page()
            page.on("dialog", lambda dialog: dialog.dismiss())
            page.on("download", lambda download: download.cancel())
            async with asyncio.timeout(self.timeout):
                response = await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
                if response and response.status >= 400:
                    raise OSError(f"HTTP {response.status}: source blocked or unavailable")
                await page.wait_for_timeout(600)
                # Fixed extraction expression only; not exposed as a tool or model parameter.
                html = await page.evaluate("() => document.documentElement.outerHTML.slice(0, 2097153)")
                if len(html.encode("utf-8")) > MAX_HTML:
                    raise ValueError("Rendered page exceeds size limit")
                observation = extract_page(html, normalize_url(page.url))
                observation.metadata["extraction"] = "rendered_dom"
                return self.remember(observation)
        finally:
            self.contexts.discard(context)
            await context.close()

    async def cancel(self):
        for context in list(self.contexts):
            await context.close()
        self.contexts.clear()

    async def close(self):
        await self.cancel()
        if self.browser:
            await self.browser.close()
        if self.proxy:
            await self.proxy.close()
        if self.driver:
            await self.driver.stop()
        self.browser = self.proxy = self.driver = None
        await super().close()


class BrowserService(ObservationBrowser):
    name = "auto"

    def __init__(self, provider="auto", timeout=25):
        super().__init__(timeout)
        self.provider = provider
        self.http = HTTPBrowserProvider(timeout)
        self.rendered = PlaywrightBrowserProvider(timeout)

    async def open(self, url):
        if self.provider == "playwright":
            page = await self.rendered.open(url)
        else:
            page = await self.http.open(url)
            if self.provider == "auto" and len(page.text.strip()) < 200 and self.rendered.installed():
                page = await self.rendered.open(url)
        return self.remember(page)

    async def cancel(self):
        await self.rendered.cancel()

    async def close(self):
        await self.http.close()
        await self.rendered.close()
        await super().close()
