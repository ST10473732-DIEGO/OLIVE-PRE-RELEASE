"""One approved visible-browser download at a time, bounded and quarantined."""

import asyncio
import mimetypes
from pathlib import Path
import time
from urllib.parse import urlsplit, urlunsplit


class BrowserDownloads:
    def __init__(self, provider):
        self.provider = provider
        self.directory = provider.profile.parent / "interactive-downloads"
        self.pending = None
        self.tab = None

    async def receive(self, page, download):
        if self.provider.stop.is_set() or self.pending is None or self.pending.done() or page is not self.provider.pages.get(self.tab):
            await download.cancel()
            await download.delete()
            return
        self.pending.set_result(download)

    async def read(self, target_id, quarantine):
        provider = self.provider
        tab, element = await provider.target(target_id)
        if self.pending is not None:
            raise ValueError("A browser download is already active")
        self.pending, self.tab = asyncio.get_running_loop().create_future(), tab
        download = transfer = None
        try:
            provider.check()
            if provider.action_guard:
                provider.action_guard()
            await element.click(timeout=500)
            deadline = time.monotonic() + 20
            while not self.pending.done():
                provider.check()
                if time.monotonic() >= deadline:
                    raise TimeoutError("No download appeared")
                await asyncio.sleep(.05)
            download = self.pending.result()
            transfer = asyncio.create_task(download.path())
            while not transfer.done():
                provider.check()
                sizes = [path.stat().st_size for path in self.directory.iterdir() if path.is_file()]
                if time.monotonic() >= deadline or sum(sizes) > 10 * 1024 * 1024:
                    raise ValueError("Download exceeded its runtime or size budget")
                await asyncio.sleep(.05)
            path = Path(await transfer)
            if not path.resolve().is_relative_to(self.directory.resolve()) or path.stat().st_size > 10 * 1024 * 1024:
                raise ValueError("Invalid browser download artifact")
            data = await asyncio.to_thread(path.read_bytes)
            parsed = urlsplit(download.url)
            if parsed.scheme not in {"http", "https"}:
                parsed = urlsplit(provider.pages[tab].url)
            source = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
            record = quarantine.store_download(source, download.suggested_filename,
                mimetypes.guess_type(download.suggested_filename)[0] or "application/octet-stream", data, approved=True)
            return {"verified": True, "download": record}
        finally:
            if download:
                await download.cancel()
                await download.delete()
            if transfer and not transfer.done():
                transfer.cancel()
                await asyncio.gather(transfer, return_exceptions=True)
            self.pending, self.tab = None, None
