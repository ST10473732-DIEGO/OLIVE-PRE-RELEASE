"""Approved Research persistence and website-scope operations."""

import asyncio
from dataclasses import asdict
from urllib.parse import urlsplit
from xml.etree import ElementTree
from ..research.urls import normalize_url
from ..research.http import fetch
from ..research.models import SourceSubscription, timestamp, identifier
from ..research.citations import render_report


class ResearchDataActions:
    def web_sources(self):
        return [
            {
                **source.to_dict(),
                "status": source.metadata.get("index_state", "unknown"),
                "chunk_count": len(source.chunk_ids),
            }
            for source in self.web_knowledge.list()
        ]

    def web_source(self, source_id):
        source = self.sources.load_all()[source_id]
        page = self.web_knowledge.page(source_id)
        return {"source": source.to_dict(), "text": page.text if page else ""}

    async def save_sources(self, session_id, source_ids, collection="OLIVE Research"):
        return await self.s.agent.tool(
            "web.learn", {"session_id": session_id, "source_ids": source_ids, "collection": collection}
        )

    async def _save_sources(self, session_id, source_ids, collection):
        if not isinstance(source_ids, list) or not 1 <= len(source_ids) <= 30:
            raise ValueError("Select 1-30 read sources")
        session = self.repository.load_all()[session_id]
        sources = {source.id: source for source in session.sources}
        results = []
        for source_id in dict.fromkeys(source_ids):
            source = sources[source_id]
            if source.status not in {"read", "evidence", "saved"} or not source.url.startswith(
                ("https://", "http://")
            ):
                raise ValueError("Only actually read web sources can be saved from Research")
            page = self.cache.get(source.url, 604800)
            if page is None and source.saved_source_id:
                page = self.web_knowledge.page(source.saved_source_id)
            if page is None:
                page = await self.browser.open(source.url)
            if page.content_hash != source.content_hash:
                raise ValueError(
                    "This source changed since Research. Review it again before saving the used material."
                )
            result = await self.web_knowledge.ingest(
                page,
                approved=True,
                project_id=session.project_id,
                collection=collection,
                session_id=session.id,
            )
            source.saved_source_id, source.status = result["source"]["id"], "saved"
            results.append(result)
            self.repository.save(session)
        self.s.publish("web_knowledge", self.web_sources())
        self.s.publish("research", session.to_dict())
        return {"results": results}

    def save_report(self, session_id, project_id, approved=False, finding_indices=None):
        if not approved:
            raise PermissionError("Saving a report requires an explicit user decision")
        if project_id not in self.s.project_repo.load_all():
            raise ValueError("Select a project")
        session = self.repository.load_all()[session_id]
        if not session.final_report:
            raise ValueError("No completed report is available")
        report = session.final_report
        if finding_indices is not None:
            if (
                not isinstance(finding_indices, list)
                or not finding_indices
                or any(type(i) is not int or not 0 <= i < len(session.findings) for i in finding_indices)
            ):
                raise ValueError("Invalid selected findings")
            report = render_report(
                session.question,
                [session.findings[i] for i in dict.fromkeys(finding_indices)],
                session.sources,
                session.evidence,
            )
        value = {
            "id": identifier(),
            "session_id": session.id,
            "project_id": project_id,
            "question": session.question,
            "report": report,
            "created_at": timestamp(),
        }
        records = self.reports.read({"schema_version": 1, "reports": []})
        records["reports"].append(value)
        self.reports.write(records)
        return value

    def project_reports(self, project_id):
        return [
            r
            for r in self.reports.read({"schema_version": 1, "reports": []})["reports"]
            if r["project_id"] == project_id
        ]

    async def scope(self, urls, mode="single", limit=5):
        return await self.s.agent.tool("web.scope", {"urls": urls, "mode": mode, "limit": limit})

    async def _scope(self, urls, mode, limit):
        if (
            mode not in {"single", "selected", "subsection", "sitemap"}
            or type(limit) is not int
            or not 1 <= limit <= 30
        ):
            raise ValueError("Invalid bounded website scope")
        if not isinstance(urls, list) or not 1 <= len(urls) <= 30:
            raise ValueError("Supply 1-30 URLs")
        urls = list(dict.fromkeys(normalize_url(url) for url in urls))
        if mode == "single":
            selected = urls[:1]
        elif mode == "selected":
            selected = urls[:limit]
        elif mode == "subsection":
            page = await self.browser.open(urls[0])
            root = urlsplit(page.url)
            prefix = root.path.rstrip("/")
            selected = [page.url]
            for link in page.links:
                target = urlsplit(link["url"])
                if target.netloc == root.netloc and (
                    target.path == prefix or target.path.startswith(prefix + "/")
                ):
                    selected.append(link["url"])
                if len(selected) >= limit:
                    break
        else:
            final_url, _, body = await fetch(urls[0], accept="application/xml,text/xml")
            if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
                raise ValueError("Sitemap declarations/entities are not supported")
            root = ElementTree.fromstring(body)
            if root.tag.rsplit("}", 1)[-1] != "urlset":
                raise ValueError("Select a page sitemap, not an unbounded sitemap index")
            origin = urlsplit(final_url).netloc
            selected = []
            for element in root.iter():
                if element.tag.rsplit("}", 1)[-1] == "loc" and element.text:
                    candidate = normalize_url(element.text)
                    if urlsplit(candidate).netloc == origin:
                        selected.append(candidate)
                    if len(selected) >= limit:
                        break
        return {
            "urls": list(dict.fromkeys(selected))[:limit],
            "estimated_pages": min(len(set(selected)), limit),
            "mode": mode,
            "note": "Only these URLs will be learned after approval; this is not a whole-domain crawl",
        }

    async def learn_urls(self, urls, project_id=None, collection="Web Knowledge"):
        return await self.s.agent.tool(
            "web.learn_urls", {"urls": urls, "project_id": project_id, "collection": collection}
        )

    async def _learn_urls(self, urls, project_id, collection):
        if not isinstance(urls, list) or not 1 <= len(urls) <= 30:
            raise ValueError("Approve a bounded list of 1-30 URLs")
        urls = list(dict.fromkeys(normalize_url(url) for url in urls))
        results = []
        for url in urls:
            try:
                page = await self.browser.open(url)
                result = await self.web_knowledge.ingest(
                    page, approved=True, project_id=project_id, collection=collection
                )
                results.append({"url": url, **result})
            except asyncio.CancelledError:
                raise
            except Exception as error:
                results.append({"url": url, "status": "failed", "error": str(error)})
            self.s.publish("web_knowledge", self.web_sources())
        return {"results": results}

    async def refresh_web(self, source_id):
        return await self.s.agent.tool("web.refresh", {"source_id": source_id})

    async def remove_web(self, source_id):
        return await self.s.agent.tool("web.remove", {"source_id": source_id})

    async def _refresh_web(self, source_id):
        source = self.sources.load_all()[source_id]
        try:
            page = await self.browser.open(source.url)
            result = await self.web_knowledge.ingest(
                page,
                approved=True,
                project_id=source.project_id,
                collection=source.collection or "",
                session_id=source.research_session_id,
            )
        except Exception as error:
            source.metadata.update(refresh_state="failed", last_error=str(error), last_checked=timestamp())
            self.sources.save(source)
            raise
        self.s.publish("web_knowledge", self.web_sources())
        return result

    def subscription_list(self):
        return self.subscriptions.read({"schema_version": 1, "subscriptions": []})["subscriptions"]

    def add_subscription(self, source_id):
        source = self.sources.load_all()[source_id]
        record = asdict(SourceSubscription(source_id, {"urls": [source.url]}, project_id=source.project_id))
        self.subscriptions.write({"schema_version": 1, "subscriptions": [*self.subscription_list(), record]})
        return record

    def downloads(self):
        return self.quarantine.list()

    async def download(self, url):
        return await self.s.agent.tool("web.download", {"url": url})

    async def read_download(self, download_id):
        return (await asyncio.to_thread(self.quarantine.read_document, download_id)).to_dict()

    async def import_download(self, download_id, project_id=None, collection="Downloads"):
        return await self.s.agent.tool(
            "web.import_download",
            {"download_id": download_id, "project_id": project_id, "collection": collection},
        )

    async def export_download(self, download_id, destination):
        return await self.s.agent.tool(
            "web.save_download", {"download_id": download_id, "destination": destination}
        )

    def remove_download(self, download_id):
        self.quarantine.remove(download_id)
        return self.downloads()

    def clear_cache(self):
        return {"removed": self.cache.cleanup(clear=True)}
