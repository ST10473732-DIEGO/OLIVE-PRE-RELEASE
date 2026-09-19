import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from olive.research.search import normalize_results, DDGSSearchProvider, SearXNGSearchProvider
from olive.research.browser import HTTPBrowserProvider, BrowserService
from olive.research.browser_proxy import PublicBrowserProxy
from olive.research.http import fetch_public


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def test_search_normalizes_and_deduplicates(self):
        values = [
            {"title": "A", "href": "https://example.com/?utm_source=x", "body": "Snippet"},
            {"title": "A copy", "url": "https://example.com/"},
            {"url": "file:///secret"},
        ]
        result = normalize_results(values, "fixture", 8)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].domain, "example.com")
        self.assertEqual(result[0].snippet, "Snippet")

    async def test_free_search_uses_bounded_maintained_adapter(self):
        with patch("ddgs.DDGS") as client:
            client.return_value.text.return_value = [{"title": "A", "href": "https://example.com/"}]
            values = await DDGSSearchProvider().search("Documentation", 3, "current")
            self.assertEqual(len(values), 1)
            self.assertEqual(client.return_value.text.call_args.kwargs["max_results"], 3)
            self.assertEqual(client.return_value.text.call_args.kwargs["timelimit"], "w")
            self.assertEqual(client.return_value.text.call_args.kwargs["backend"], "bing")

    async def test_search_failures_are_visible_without_bypass(self):
        with patch("ddgs.DDGS") as client:
            client.return_value.text.side_effect = RuntimeError("Rate limited")
            with self.assertRaisesRegex(RuntimeError, "Rate limited"):
                await DDGSSearchProvider().search("Question")
            self.assertEqual(client.return_value.text.call_count, 1)

    async def test_searxng_json_response(self):
        with patch(
            "olive.research.search.fetch",
            new=AsyncMock(
                return_value=(
                    "https://search.example.com/search",
                    "application/json",
                    b'{"results":[{"title":"Docs","url":"https://example.com/docs"}]}',
                )
            ),
        ):
            values = await SearXNGSearchProvider("https://search.example.com").search("Documentation")
            self.assertEqual(values[0].provider, "searxng")

    async def test_browser_read_links_and_follow(self):
        browser = HTTPBrowserProvider()
        with patch(
            "olive.research.browser.fetch",
            new=AsyncMock(
                return_value=(
                    "https://example.com/",
                    "text/html",
                    b'<main><p>Documentation content.</p><a href="/next">Next</a></main>',
                )
            ),
        ) as fetch:
            page = await browser.open("https://example.com/")
            self.assertEqual((await browser.read(page.url)).content_hash, page.content_hash)
            self.assertEqual(fetch.await_count, 1)
            self.assertEqual((await browser.links(page.url))[0]["url"], "https://example.com/next")
            self.assertNotIn("text", await browser.page_info(page.url))
            with self.assertRaises(ValueError):
                await browser.follow_link(page.url, "https://unknown.example.com/")

    async def test_browser_does_not_interpret_download_as_page(self):
        with patch(
            "olive.research.browser.fetch",
            new=AsyncMock(
                return_value=("https://example.com/program.exe", "application/octet-stream", b"MZfile")
            ),
        ):
            with self.assertRaisesRegex(ValueError, "quarantine"):
                await HTTPBrowserProvider().open("https://example.com/program.exe")

    async def test_render_fallback_only_for_thin_successful_pages(self):
        browser = BrowserService()
        with (
            patch.object(browser.http, "open", new=AsyncMock(side_effect=OSError("HTTP 403"))),
            patch.object(browser.rendered, "open", new=AsyncMock()) as rendered,
        ):
            with self.assertRaises(OSError):
                await browser.open("https://example.com/")
            rendered.assert_not_awaited()

    def test_http_private_dns_result_never_connects(self):
        with (
            patch(
                "olive.research.http.socket.getaddrinfo",
                return_value=[(None, None, None, None, ("127.0.0.1", 443))],
            ),
            patch("olive.research.http.http.client.HTTPSConnection") as connection,
        ):
            with self.assertRaises(ValueError):
                fetch_public("https://example.com/")
            connection.assert_not_called()

    async def test_browser_proxy_blocks_private_connect(self):
        reader = asyncio.StreamReader()
        reader.feed_data(b"CONNECT 127.0.0.1:443 HTTP/1.1\r\n\r\n")
        reader.feed_eof()

        class Writer:
            def __init__(self):
                self.output = b""

            def write(self, data):
                self.output += data

            async def drain(self):
                return None

            def close(self):
                return None

            async def wait_closed(self):
                return None

        writer = Writer()
        with patch("olive.research.browser_proxy.asyncio.open_connection", new=AsyncMock()) as connect:
            await PublicBrowserProxy().handle(reader, writer)
            connect.assert_not_awaited()
        self.assertIn(b"502", writer.output)


if __name__ == "__main__":
    unittest.main()
