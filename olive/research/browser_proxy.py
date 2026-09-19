"""Ephemeral browser egress proxy: resolve once, reject private IPs, connect to that IP.

The proxy holds no credentials and never accepts filesystem or tool commands.
TLS remains end-to-end between Chromium and the public source.
"""

import asyncio
from contextlib import suppress
from urllib.parse import urlsplit
from .http import public_addresses
from .urls import normalize_url


class PublicBrowserProxy:
    def __init__(self):
        self.server = None
        self.tasks = set()
        self.connections = asyncio.Semaphore(12)

    async def start(self):
        self.server = await asyncio.start_server(self.handle, "127.0.0.1", 0, limit=16384)
        return f"http://127.0.0.1:{self.server.sockets[0].getsockname()[1]}"

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        remote = None
        try:
            async with self.connections, asyncio.timeout(65):
                header = await reader.readuntil(b"\r\n\r\n")
                method, target, _ = header.split(b"\r\n", 1)[0].decode("ascii").split(" ", 2)
                if method == "CONNECT":
                    url = normalize_url("https://" + target)
                elif method in {"GET", "HEAD"}:
                    url = normalize_url(target)
                    if urlsplit(url).scheme != "http":
                        raise ValueError("HTTPS requires CONNECT")
                else:
                    raise ValueError("Research browser requests must be read-only")
                parts = urlsplit(url)
                port = parts.port or (443 if parts.scheme == "https" else 80)
                addresses = await asyncio.to_thread(public_addresses, parts.hostname, port)
                upstream, remote = await asyncio.open_connection(addresses[0], port)
                if method == "CONNECT":
                    writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    await writer.drain()
                else:
                    path = parts.path + ("?" + parts.query if parts.query else "")
                    remote.write(
                        f"{method} {path} HTTP/1.1\r\nHost: {parts.netloc}\r\nUser-Agent: OLIVE-Research/3.3\r\nConnection: close\r\n\r\n".encode(
                            "ascii"
                        )
                    )
                    await remote.drain()

                async def pipe(source, destination):
                    total = 0
                    while chunk := await source.read(32768):
                        total += len(chunk)
                        if total > 12 * 1024 * 1024:
                            raise ValueError("Browser connection exceeded resource limit")
                        destination.write(chunk)
                        await destination.drain()

                forwarding = [
                    asyncio.create_task(pipe(reader, remote)),
                    asyncio.create_task(pipe(upstream, writer)),
                ]
                try:
                    done, _ = await asyncio.wait(forwarding, return_when=asyncio.FIRST_COMPLETED)
                    for completed in done:
                        completed.result()
                finally:
                    for pending in forwarding:
                        pending.cancel()
                    await asyncio.gather(*forwarding, return_exceptions=True)
        except (OSError, ValueError, TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            # A denied/failed network request is returned as a network failure, never retried via host access.
            with suppress(OSError):
                writer.write(b"HTTP/1.1 502 Research destination unavailable\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
        finally:
            if remote:
                remote.close()
                with suppress(OSError):
                    await remote.wait_closed()
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()
            self.tasks.discard(task)

    async def close(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
