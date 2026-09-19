"""Bounded research lifecycle. Gateway exposes authorized observations, not host tools."""

import asyncio
import time
import re
from urllib.parse import urlsplit
from .models import ResearchSource, PageObservation, SearchResult, timestamp
from .settings import ResearchSettings
from .evidence import extract_evidence, source_quality, rank_sources, potential_conflicts
from .planner import freshness_requirement
from .urls import normalize_url


class ResearchPaused(Exception):
    pass


def requested_hosts(question):
    sites = re.findall(r"\bsite:([a-zA-Z0-9.-]+)", question)
    if not sites:
        sites = [urlsplit(value.rstrip(".,;!?)\"'")).hostname or "" for value in re.findall(r"https?://[^\s<>]+", question)]
    return {site.rstrip(".").lower() for site in sites if site}


def in_requested_scope(url, question):
    sites = requested_hosts(question)
    if not sites:
        return True
    host = (urlsplit(url).hostname or "").lower()
    return any(host == requested or host.endswith("." + requested) for requested in sites)


class ResearchOrchestrator:
    def __init__(self, repository, planner, synthesizer, gateway, cache, emit):
        self.repository, self.planner, self.synthesizer = repository, planner, synthesizer
        self.gateway, self.cache, self.emit = gateway, cache, emit
        self.active = None
        self.current = None
        self.pause_requested = False
        self.shutting_down = False

    def publish(self, session):
        session.updated_at = timestamp()
        self.repository.save(session)
        self.emit("research", session.to_dict())

    def phase(self, session, state, activity):
        session.transition(state, activity)
        self.publish(session)

    def checkpoint(self):
        if self.pause_requested:
            raise ResearchPaused()

    def pause(self):
        self.pause_requested = True
        if self.current:
            self.current.activity = "Pausing after current operations"
            self.publish(self.current)

    def cancel(self):
        if self.active:
            self.active.cancel()

    async def shutdown(self):
        self.shutting_down = True
        self.cancel()
        if self.active:
            await asyncio.gather(self.active, return_exceptions=True)

    async def run(self, session):
        if self.active:
            raise ValueError("A Research session is already active")
        settings = ResearchSettings.validated(session.settings)
        self.active = asyncio.current_task()
        self.current = session
        self.pause_requested = False
        started = time.monotonic()
        remaining = max(0, settings.timeout - session.elapsed_seconds)
        try:
            if remaining <= 0:
                raise TimeoutError("Research runtime limit reached")
            async with asyncio.timeout(remaining):
                await self.investigate(session, settings)
        except ResearchPaused:
            self.phase(session, "paused", "Paused; resume explicitly")
        except asyncio.CancelledError:
            self.phase(
                session,
                "paused" if self.shutting_down else "cancelled",
                "Interrupted; resume explicitly" if self.shutting_down else "Research cancelled",
            )
        except TimeoutError:
            session.error = "Research reached its runtime limit; gathered evidence is retained"
            self.phase(session, "paused", "Runtime limit reached")
        except Exception as error:
            session.error = str(error) or type(error).__name__
            self.phase(session, "paused" if session.evidence else "failed", "Research needs attention")
        finally:
            session.elapsed_seconds += time.monotonic() - started
            self.publish(session)
            self.active = self.current = None
        return session.to_dict()

    async def investigate(self, session, settings):
        session.error = ""
        self.checkpoint()
        if not session.plan:
            self.phase(session, "planning", "Planning research...")
            session.plan = await self.planner.plan(
                session.question, session.context, timeout=min(180, settings.timeout)
            )
            self.publish(session)
        self.checkpoint()
        max_searches, max_pages = settings.limits()
        known = {source.url for source in session.sources}
        for candidate in re.findall(r"https?://[^\s<>]+", session.question):
            url = normalize_url(candidate.rstrip(".,;!?)\"'"))
            if (
                url not in known
                and len(session.sources) < max_pages
                and in_requested_scope(url, session.question)
            ):
                session.sources.append(
                    ResearchSource(
                        url,
                        url,
                        domain=urlsplit(url).hostname,
                        metadata={"origin": "explicit_user_url", "depth": 0},
                    )
                )
                known.add(url)
        freshness = session.plan.get("freshness_requirement", freshness_requirement(session.question))
        queries = session.plan["search_queries"][:max_searches]
        domains = requested_hosts(session.question)
        if len(domains) == 1:
            domain = next(iter(domains))
            queries = [re.sub(r"\bsite:[a-zA-Z0-9.-]+", "", query).strip() + " site:" + domain for query in queries]
        for query in queries:
            self.checkpoint()
            if any(item["query"] == query for item in session.queries):
                continue
            if len(session.queries) >= max_searches or len(session.sources) >= max_pages:
                break
            self.phase(session, "searching", "Searching for " + query)
            attempt = {"query": query, "status": "searching", "provider": settings.search_provider}
            session.queries.append(attempt)
            self.publish(session)
            try:
                values = await self.gateway.search(
                    query, limit=min(12, max(5, max_pages)), freshness=freshness
                )
                results = [
                    value if isinstance(value, SearchResult) else SearchResult(**value) for value in values
                ]
                attempt["status"] = "completed"
                attempt["result_count"] = len(results)
                known = {s.url for s in session.sources}
                remaining_queries = max(1, len(queries) - len(session.queries) + 1)
                allowance = max(1, (max_pages - len(session.sources)) // remaining_queries)
                selected = 0
                for result in rank_sources(results, session.question, freshness):
                    url = normalize_url(result.url)
                    if not in_requested_scope(url, session.question):
                        continue
                    if url not in known and len(session.sources) < max_pages:
                        session.sources.append(
                            ResearchSource(
                                url,
                                result.title,
                                domain=urlsplit(url).hostname,
                                publication_date=result.publication_date,
                                metadata={"search_provider": result.provider, "query": query, "depth": 0},
                            )
                        )
                        known.add(url)
                        selected += 1
                        if selected >= allowance:
                            break
            except asyncio.CancelledError:
                attempt["status"] = "cancelled"
                raise
            except Exception as error:
                attempt.update(status="failed", error=str(error))
            self.publish(session)
            await self.read_selected(session, settings, freshness, max_pages)
        await self.read_selected(session, settings, freshness, max_pages)
        self.checkpoint()
        self.phase(session, "evaluating", "Comparing sources and checking evidence...")
        session.context["potential_disagreements"] = potential_conflicts(session.evidence)
        self.publish(session)
        if not session.evidence:
            raise ValueError(
                "No relevant readable evidence was gathered. Search snippets are not treated as read sources."
            )
        self.checkpoint()
        self.phase(session, "synthesizing", "Synthesizing cited findings...")
        findings, report = await self.synthesizer.synthesize(session, timeout=min(240, settings.timeout))
        self.checkpoint()
        session.findings, session.final_report = findings, report
        evidence = {e.id: e for e in session.evidence}
        used = {evidence[eid].source_id for finding in findings for eid in finding["evidence_ids"]}
        for source in session.sources:
            if source.id in used and source.status == "read":
                source.status = "evidence"
        self.phase(
            session, "completed", "Research complete; sources are not automatically saved to Knowledge"
        )

    async def read_selected(self, session, settings, freshness, max_pages):
        semaphore = asyncio.Semaphore(settings.page_concurrency)
        while pending := [s for s in session.sources if s.status == "visited"]:
            self.checkpoint()
            self.phase(session, "reading", "Reading selected sources...")

            async def read(source):
                async with semaphore:
                    self.checkpoint()
                    source.status = "reading"
                    session.activity = "Reading " + source.domain
                    self.publish(session)
                    try:
                        age = (
                            0
                            if freshness == "current"
                            else min(settings.cache_lifetime, 86400)
                            if freshness == "recent"
                            else settings.cache_lifetime
                        )
                        page = self.cache.get(source.url, age)
                        if page is None:
                            value = await asyncio.wait_for(
                                self.gateway.open(source.url), settings.page_timeout + 2
                            )
                            page = value if isinstance(value, PageObservation) else PageObservation(**value)
                            if not in_requested_scope(page.url, session.question):
                                raise ValueError("Source redirected outside the requested documentation scope")
                            self.cache.put(page)
                        if not in_requested_scope(page.url, session.question):
                            raise ValueError("Cached source is outside the requested documentation scope")
                        source.title, source.url = page.title, page.url
                        source.domain = urlsplit(page.url).hostname
                        for field in (
                            "canonical_url",
                            "content_hash",
                            "retrieved_at",
                            "author",
                            "publication_date",
                            "updated_date",
                            "content_type",
                        ):
                            setattr(source, field, getattr(page, field))
                        source.status = "read"
                        source.quality = source_quality(page)
                        duplicate = next(
                            (
                                s
                                for s in session.sources
                                if s.id != source.id
                                and s.content_hash == source.content_hash
                                and s.status in {"read", "evidence", "saved"}
                            ),
                            None,
                        )
                        if duplicate:
                            source.duplicate_of = duplicate.id
                        else:
                            session.evidence.extend(
                                extract_evidence(page, source.id, session.plan["subquestions"], question=session.question)
                            )
                            depth = source.metadata.get("depth", 0)
                            if depth < settings.max_link_depth and len(session.queries) >= min(
                                settings.max_searches, len(session.plan["search_queries"])
                            ):
                                candidates = [
                                    SearchResult(link["text"], link["url"], rank=i + 1)
                                    for i, link in enumerate(page.links)
                                ]
                                known = {s.url for s in session.sources}
                                for result in rank_sources(candidates, session.question)[:2]:
                                    if not in_requested_scope(result.url, session.question):
                                        continue
                                    if result.url not in known and len(session.sources) < max_pages:
                                        session.sources.append(
                                            ResearchSource(
                                                result.url,
                                                result.title,
                                                domain=urlsplit(result.url).hostname,
                                                metadata={"depth": depth + 1, "linked_from": source.id},
                                            )
                                        )
                                        known.add(result.url)
                    except asyncio.CancelledError:
                        source.status = "visited"
                        raise
                    except Exception as error:
                        source.status, source.error = "failed", str(error)
                    self.publish(session)

            tasks = [asyncio.create_task(read(source)) for source in pending]
            try:
                await asyncio.gather(*tasks)
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
