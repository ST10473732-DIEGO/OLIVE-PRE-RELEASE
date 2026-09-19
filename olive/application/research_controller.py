"""Shared Research application state; all outbound actions use registered tools."""

import asyncio
from ..research.models import ResearchSession, ResearchSource
from ..research.settings import ResearchSettings
from ..research.repository import ResearchRepository
from ..research.planner import ResearchPlanner, freshness_requirement
from ..research.citations import ResearchSynthesizer
from ..research.orchestrator import ResearchOrchestrator
from ..research.cache import ResearchCache
from ..research.browser import BrowserService, PlaywrightBrowserProvider
from ..research.search import DDGSSearchProvider, SearXNGSearchProvider
from ..research.web_knowledge import WebKnowledgeService
from ..research.quarantine import DownloadQuarantine
from ..research.evidence import extract_evidence
from ..research.extraction import content_hash
from ..research.models import PageObservation
from ..knowledge.learning_service import LearningService
from ..storage.knowledge_source_repository import KnowledgeSourceRepository
from ..storage.json_store import JsonStore
from .research_data import ResearchDataActions


class AuthorizedResearchGateway:
    def __init__(self, services):
        self.services = services

    async def search(self, query, limit=8, freshness="any"):
        result = await self.services.agent.tool(
            "web.search", {"query": query, "limit": limit, "freshness": freshness}
        )
        return result["results"]

    async def open(self, url):
        return await self.services.agent.tool("web.open", {"url": url})


class ResearchController(ResearchDataActions):
    def __init__(self, services):
        self.s = services
        self.repository = ResearchRepository(services.data_dir / "research_sessions.json")
        self.repository.recover_interrupted()
        self.cache = ResearchCache(services.data_dir / "research_cache")
        self.sources = KnowledgeSourceRepository(services.data_dir / "knowledge_sources.json")
        self.learning = LearningService(self.sources)
        self.web_knowledge = WebKnowledgeService(
            self.sources, self.learning, services.rag, services.data_dir, services.project_repo
        )
        self.quarantine = DownloadQuarantine(services.data_dir / "quarantine")
        self.reports = JsonStore(services.data_dir / "research_reports.json")
        self.subscriptions = JsonStore(services.data_dir / "web_subscriptions.json")
        self.browser = BrowserService()
        self.search_provider = DDGSSearchProvider()
        self.configured = None
        self.starting = None
        self.preparing_session = None
        self.pause_start = False
        self.configuration_lock = asyncio.Lock()
        self.orchestrator = ResearchOrchestrator(
            self.repository,
            ResearchPlanner(services.ollama, services.model_router),
            ResearchSynthesizer(services.ollama, services.model_router),
            AuthorizedResearchGateway(services),
            self.cache,
            services.publish,
        )
        from ..research.tools import research_tools

        for tool in research_tools(self):
            services.tool_registry.register(tool)

    def settings(self):
        return ResearchSettings.validated(self.s.settings.get("research", {}))

    def preferences(self):
        return self.settings().to_dict()

    async def configure(self):
        settings = self.settings()
        async with self.configuration_lock:
            if settings != self.configured:
                await self.browser.close()
                self.browser = BrowserService(settings.browser_provider, settings.page_timeout)
                self.search_provider = (
                    SearXNGSearchProvider(settings.search_endpoint)
                    if settings.search_provider == "searxng"
                    else DDGSSearchProvider()
                )
                self.configured = settings
        return settings

    def history(self):
        return [
            session.to_dict()
            for session in sorted(
                self.repository.load_all().values(), key=lambda s: s.updated_at, reverse=True
            )
        ]

    def get(self, session_id):
        if self.orchestrator.current and self.orchestrator.current.id == session_id:
            return self.orchestrator.current.to_dict()
        return self.repository.load_all()[session_id].to_dict()

    def create(self, question, project_id=None, context=None, depth=None):
        if not isinstance(question, str) or not 1 <= len(question.strip()) <= 4000:
            raise ValueError("Enter a research question of at most 4000 characters")
        if project_id and project_id not in self.s.project_repo.load_all():
            raise ValueError("Unknown project")
        settings = self.settings().to_dict()
        if depth:
            settings["depth"] = depth
        settings = ResearchSettings.validated(settings).to_dict()
        # Explicit Studio context is bounded and has no authority or executable fields.
        context = context or {}
        if not isinstance(context, dict) or set(context) - {"error", "language", "file", "selection"}:
            raise ValueError("Unknown Research context fields")
        bounded = {key: str(value)[:4000] for key, value in context.items()}
        session = ResearchSession(
            question.strip(),
            project_id=project_id,
            settings=settings,
            context={"untrusted_studio_context": bounded},
        )
        self.repository.save(session)
        self.s.publish("research", session.to_dict())
        return session.to_dict()

    async def start(self, session_id=None, question=None, project_id=None, context=None, depth=None):
        if self.starting or self.orchestrator.active:
            raise ValueError("Pause or finish the active Research session first")
        self.starting = asyncio.current_task()
        self.pause_start = False
        try:
            return await self._start(session_id, question, project_id, context, depth)
        except asyncio.CancelledError:
            if self.preparing_session:
                self.preparing_session.transition(
                    "paused" if self.pause_start else "cancelled", "Preparation interrupted"
                )
                self.repository.save(self.preparing_session)
                self.s.publish("research", self.preparing_session.to_dict())
                return self.preparing_session.to_dict()
            raise
        finally:
            self.starting = self.preparing_session = None

    async def _start(self, session_id=None, question=None, project_id=None, context=None, depth=None):
        if self.orchestrator.active:
            raise ValueError("Pause or finish the active Research session first")
        if session_id is None:
            session_id = self.create(question, project_id, context, depth)["id"]
        session = self.repository.load_all()[session_id]
        self.preparing_session = session
        if session.status in {"completed", "cancelled"}:
            raise ValueError("Start new Research to repeat a completed or cancelled investigation")
        await self.configure()
        if not session.plan and not session.context.get("local_context_loaded"):
            await self.local_context(session)
        return await self.orchestrator.run(session)

    async def resume(self, session_id):
        return await self.start(session_id=session_id)

    async def follow_up(self, session_id, question, project_id=None):
        """Carry bounded planning context forward without promoting reports to evidence."""
        if self.starting or self.orchestrator.active:
            raise ValueError("Pause or finish the active Research session first")
        previous = self.repository.load_all().get(session_id)
        if previous is None or previous.project_id != project_id:
            raise ValueError("Which research investigation in this project should I follow up?")
        if previous.status != "completed" or not previous.final_report:
            raise ValueError("Finish the previous research investigation before following up.")
        created = self.create(question, project_id)
        session = self.repository.load_all()[created["id"]]
        session.context["untrusted_prior_research"] = {
            "session_id": previous.id,
            "question": previous.question[:4000],
            "report_excerpt": previous.final_report[:6000],
            "report_truncated": len(previous.final_report) > 6000,
            "usage": "Background for planning only. Recheck claims using newly retrieved evidence.",
        }
        self.repository.save(session)
        return await self.start(session_id=session.id)

    def pause(self):
        if self.starting and not self.orchestrator.active:
            self.pause_start = True
            self.starting.cancel()
        self.orchestrator.pause()

    def cancel(self):
        if self.starting and not self.orchestrator.active:
            self.starting.cancel()
        self.orchestrator.cancel()

    async def local_context(self, session):
        project = self.s.project_repo.load_all().get(session.project_id)
        chats = [chat for chat in self.s.chats.values() if project and chat.project_id == project.id]
        if not project:
            chats = [self.s.chats[self.s.current_chat_id]]
        snippets = []
        seed_limit = min(3, ResearchSettings.validated(session.settings).limits()[1] - 1)
        for chat in chats[:3]:
            for hit in await self.s.rag.retrieve(chat.id, session.question, 2):
                snippets.append({"source": hit.source_label, "text": hit.content[:1200]})
                source = ResearchSource(
                    "olive-knowledge:" + hit.document_id + ":" + str(hit.chunk_index),
                    hit.source_label,
                    status="read",
                    content_hash=content_hash(hit.content),
                    metadata={"source_type": "local_knowledge", "document_id": hit.document_id},
                )
                page = PageObservation(source.url, source.title, hit.content, source.content_hash)
                session.sources.append(source)
                session.evidence.extend(extract_evidence(page, source.id, [session.question], limit=1))
                if len(session.sources) >= seed_limit:
                    break
            if len(session.sources) >= seed_limit:
                break
        memories = self.s.memory.search_for_project(
            session.question, session.project_id, project.memory_ids if project else [], limit=3
        )
        session.context.update(
            local_knowledge=snippets[:4],
            relevant_memories=[m.content[:500] for m, _ in memories],
            project_description=project.description[:1500] if project else "",
            local_context_loaded=True,
        )
        freshness = freshness_requirement(session.question)
        age = (
            0
            if freshness == "current"
            else min(self.settings().cache_lifetime, 86400)
            if freshness == "recent"
            else self.settings().cache_lifetime
        )
        for saved, page in await self.web_knowledge.reusable_pages(
            session.question, session.project_id, age, limit=2
        ):
            if len(session.sources) >= seed_limit:
                break
            source = ResearchSource(
                page.url,
                page.title,
                status="read",
                content_hash=page.content_hash,
                retrieved_at=page.retrieved_at,
                publication_date=page.publication_date,
                saved_source_id=saved["id"],
                metadata={"reused_knowledge": True},
            )
            session.sources.append(source)
            session.evidence.extend(extract_evidence(page, source.id, [session.question], limit=2))
        self.repository.save(session)

    def diagnostics(self):
        sessions = self.repository.load_all().values()
        settings = self.settings()
        return {
            "research_status": "active" if self.orchestrator.active else "ready",
            "research_browser": settings.browser_provider,
            "research_search": settings.search_provider,
            "research_browser_availability": PlaywrightBrowserProvider.availability(),
            "research_active_sessions": int(self.orchestrator.active is not None),
            "research_failed_sessions": sum(s.status == "failed" for s in sessions),
            "research_cache": self.cache.status(),
            "web_knowledge_sources": len(self.web_knowledge.list()),
        }

    async def shutdown(self):
        if self.starting and not self.orchestrator.active:
            self.pause_start = True
            task = self.starting
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await self.orchestrator.shutdown()
        await self.browser.close()
