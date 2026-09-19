import asyncio
import json
from urllib.parse import urlsplit, urlencode
from .models import SearchResult
from .urls import normalize_url
from .http import fetch


def normalize_results(values, provider, limit):
    results, seen = [], set()
    for value in values:
        if not isinstance(value, dict):
            continue
        try:
            url = normalize_url(value.get("url") or value.get("href") or "")
        except ValueError:
            continue
        if url in seen:
            continue
        seen.add(url)
        results.append(
            SearchResult(
                str(value.get("title") or url)[:500],
                url,
                str(value.get("snippet") or value.get("body") or value.get("content") or "")[:2000],
                provider,
                len(results) + 1,
                value.get("publishedDate") or value.get("publication_date"),
                urlsplit(url).hostname,
            )
        )
        if len(results) >= limit:
            break
    return results


class DDGSSearchProvider:
    """Maintained free-search adapter; no challenge solver or access bypass."""

    name = "ddgs"

    async def search(self, query, limit=8, freshness="any"):
        if not isinstance(query, str) or not query.strip() or len(query) > 1000:
            raise ValueError("Search query must contain 1-1000 characters")
        limit = min(20, max(1, int(limit)))

        def search():
            from ddgs import DDGS

            return DDGS(timeout=12, verify=True).text(
                query,
                max_results=limit,
                backend="bing",
                timelimit="w" if freshness == "current" else "m" if freshness == "recent" else None,
            )

        values = await asyncio.wait_for(asyncio.to_thread(search), 16)
        return normalize_results(values, self.name, limit)


class SearXNGSearchProvider:
    name = "searxng"

    def __init__(self, endpoint):
        self.endpoint = normalize_url(endpoint).rstrip("/")

    async def search(self, query, limit=8, freshness="any"):
        if not isinstance(query, str) or not query.strip() or len(query) > 1000:
            raise ValueError("Invalid search query")
        parameters = {"q": query, "format": "json", "categories": "general"}
        if freshness != "any":
            parameters["time_range"] = "week" if freshness == "current" else "month"
        _, kind, body = await fetch(
            self.endpoint + "/search?" + urlencode(parameters), accept="application/json"
        )
        value = json.loads(body)
        if not isinstance(value, dict) or not isinstance(value.get("results"), list):
            raise ValueError("Invalid SearXNG response; enable its JSON search API")
        return normalize_results(value["results"], self.name, min(20, max(1, limit)))
