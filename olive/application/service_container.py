from __future__ import annotations
from pathlib import Path
import logging
import asyncio
from ..config import DATA_DIR, EMBEDDING_MODEL
from ..models import Chat
from ..services.chat_service import ChatService
from ..services.document_service import DocumentService
from ..services.ocr_service import OCRService
from ..services.document_health_service import DocumentHealthService
from ..services.ollama_service import OllamaService, choose_default_chat_model
from ..services.model_registry import ModelCapabilityRegistry
from ..services.rag_service import RAGService
from ..storage import ChatRepository, IndexingJobRepository, MemoryRepository, SettingsRepository
from ..services.indexing_job_service import IndexingJobService
from ..services.memory_service import MemoryService
from ..services.memory_suggestion_service import MemorySuggestionService
from ..services.diagnostics_service import DiagnosticsService
from ..services.grounding_service import GroundingService
from ..services.backup_service import BackupService
from ..services.indexing_scheduler import IndexingScheduler
from ..services.maintenance_service import MaintenanceService
from ..storage.migration import migrate_legacy_data
from ..storage.rag_store import RAGStore
from ..themes import DEFAULT_THEME, THEMES, get_theme
from ..services.run_service import RunService
from ..services.problem_service import ProblemService
from ..agent.audit_service import AuditService
from ..agent.confirmation_service import ConfirmationService
from ..agent.deterministic_planner import DeterministicPlanner
from ..agent.workspace_planner import CompositePlanner, WorkspacePlanner
from ..agent.structured_coding_planner import StructuredCodingPlanner
from ..agent.model_router import ModelRouter
from ..agent.executor import ToolExecutor
from ..agent.orchestrator import AgentOrchestrator
from ..agent.permission_service import PermissionService
from ..agent.tool_registry import ToolRegistry
from ..storage.agent_task_repository import AgentTaskRepository
from ..storage.project_repository import ProjectRepository
from ..storage.workspace_repository import WorkspaceRepository
from ..services.workspace_service import WorkspaceService
from ..services.repository_service import RepositoryService
from ..services.code_index_service import CodeIndexService
from ..services.repository_map_service import RepositoryMapService
from ..services.code_retrieval_service import CodeRetrievalService
from ..services.editor_intelligence_service import EditorIntelligenceService
from ..services.test_result_service import TestResultService
from ..services.application_observation_service import ApplicationObservationService
from ..services.model_metrics_service import ModelMetricsService
from ..services.coding_context_service import CodingContextService
from ..services.diff_review_service import DiffReviewService
from ..services.dependency_service import DependencyService
from ..services.syntax_highlight_service import SyntaxHighlightService
from ..services.language_server_service import LanguageServerService
from ..services.build_session_service import BuildSessionService
from ..services.web_preview_service import WebPreviewService
from ..services.checkpoint_service import CheckpointService
from ..services.build_test_service import BuildAndTestService
from ..services.ide_service import IDEService
from ..tools import (
    TerminalRunTool,
    StudioRunTool,
    code_tools,
    filesystem_tools,
    git_tools,
    ide_tools,
    system_tools,
    workspace_tools,
)
import inspect
from copy import deepcopy

logger = logging.getLogger(__name__)


class ServiceContainer:
    """One service graph, owned exclusively by the application runtime thread."""

    def __init__(self, emit, confirmation_handler, data_dir=None, migrate=True):
        self.emit = emit
        data = Path(data_dir) if data_dir is not None else DATA_DIR
        self.data_dir = data
        data.mkdir(parents=True, exist_ok=True)
        self.chat_repo = ChatRepository(data / "chats.json")
        self.settings_repo = SettingsRepository(
            data / "settings.json", data / "model_defaults.json", data / "model_aliases.json"
        )
        self.migration_actions = migrate_legacy_data() if migrate and data_dir is None else []

        self.settings = self.settings_repo.load()
        self.settings.setdefault("preferred_name", "Diego")
        self.model_defaults = self.settings_repo.load_model_defaults()
        self.model_aliases = self.settings_repo.load_model_aliases()
        self.theme_name = self.settings.get("theme", DEFAULT_THEME)
        if self.theme_name not in THEMES and self.theme_name != "Light":
            self.theme_name = DEFAULT_THEME
            self.settings["theme"] = DEFAULT_THEME
        self.colors = get_theme(self.theme_name)

        from ..authority.owner import OwnerPolicy
        self.owner_policy = OwnerPolicy(lambda: self.settings)
        self.ollama = OllamaService()
        from ..services.local_ollama_runtime import LocalOllamaRuntime
        self.local_ollama_runtime = LocalOllamaRuntime(self.ollama.host)
        self.model_registry = ModelCapabilityRegistry(self.ollama)
        self.rag_store = RAGStore(data / "rag.sqlite3")
        self.rag = RAGService(
            self.rag_store,
            self.ollama,
            self.settings.get("embedding_model", EMBEDDING_MODEL),
            semantic_weight=float(self.settings.get("rag_semantic_weight", 0.65)),
            lexical_weight=float(self.settings.get("rag_lexical_weight", 0.35)),
            minimum_score=float(self.settings.get("rag_minimum_score", 0.08)),
        )
        self.memory = MemoryService(MemoryRepository(data / "memories.json"))
        self.memory_suggestions = MemorySuggestionService(self.memory, self.ollama)
        self.indexing_jobs = IndexingJobService(IndexingJobRepository(data / "indexing_jobs.json"))
        self.indexing_jobs.recover_interrupted()
        self.documents = DocumentService(
            OCRService(self.settings.get("ocr_executable") or None), cache_dir=data / "attachments"
        )
        self.document_health = DocumentHealthService()
        self.chat_service = ChatService(self.ollama, self.rag, memory=self.memory)
        self.chat_service.pipeline.preferences = lambda: self.settings
        from ..services.deep_documents import DeepDocuments
        self.chat_service.pipeline.deep = DeepDocuments(self)
        self.diagnostics = DiagnosticsService(
            self.ollama, self.model_registry, self.rag, self.memory, self.indexing_jobs, self.documents.ocr
        )
        self.grounding = GroundingService()
        self.backups = BackupService(data, data / "backups")
        self.indexing_scheduler = IndexingScheduler(
            self.indexing_jobs,
            self._execute_indexing_job,
            int(self.settings.get("max_indexing_workers", 1)),
        )
        self.maintenance = MaintenanceService(self.rag_store, self.indexing_jobs, self.document_health)
        self.project_repo = ProjectRepository(data / "projects.json")
        self.workspace_repo = WorkspaceRepository(data / "workspaces.json")
        self.workspace_service = WorkspaceService(self.workspace_repo)
        self.owner_policy.workspace_repo = self.workspace_repo
        self.repository_service = RepositoryService()
        self.code_index_service = CodeIndexService()
        self.repository_maps = RepositoryMapService(
            self.code_index_service, repository=self.repository_service
        )
        self.code_retrieval = CodeRetrievalService(
            self.ollama,
            self.settings.get("embedding_model", EMBEDDING_MODEL),
            data / "code_indexes" / "semantic_code.json",
        )
        self.build_test_service = BuildAndTestService()
        self.ide_service = IDEService()
        self.checkpoints = CheckpointService(data / "task_checkpoints")
        self.run_service = RunService()
        from ..services.terminal_session_service import TerminalSessionService

        self.terminal_sessions = TerminalSessionService(data / "terminal_sessions.json")
        self.problem_service = ProblemService()
        self.editor_intelligence = EditorIntelligenceService()
        self.test_results = TestResultService()
        self.application_observations = ApplicationObservationService()
        self.model_metrics = ModelMetricsService()
        from ..services.model_residency_service import ModelResidencyService
        from ..services.model_benchmark_service import ModelBenchmarkService
        self.model_residency = ModelResidencyService(self.ollama, lambda: self.settings.get("model_policy", {}))
        self.model_benchmarks = ModelBenchmarkService(self.ollama, self.model_registry, data / "model_benchmarks.json", self.publish)
        self.ollama.residency = self.model_residency
        self.ollama.metrics = self.model_metrics
        self.coding_context = CodingContextService()
        self.diff_review = DiffReviewService()
        self.dependencies = DependencyService()
        self.syntax_highlighting = SyntaxHighlightService()
        self.language_servers = LanguageServerService()
        self.build_sessions = BuildSessionService()
        self.web_preview = WebPreviewService()
        self.agent_task_repo = AgentTaskRepository(data / "agent_tasks.json")
        self.agent_task_repo.recover_interrupted()
        self.permissions = PermissionService(data / "permissions.json")
        from ..connect.service import DesktopDeviceService
        self.connect = DesktopDeviceService(data)
        self.agent_audit = AuditService(data / "agent_audit.jsonl")
        self.tool_registry = ToolRegistry()
        for tool in [
            *filesystem_tools(),
            TerminalRunTool(),
            *system_tools(),
            *code_tools(self.workspace_repo, self.checkpoints),
            *git_tools(self.repository_service, self.workspace_repo),
            *ide_tools(self.workspace_repo),
            *workspace_tools(self.workspace_repo),
            StudioRunTool(self.run_service, self.workspace_repo),
        ]:
            self.tool_registry.register(tool)
        self.confirmations = ConfirmationService(confirmation_handler)
        self.agent_executor = ToolExecutor(
            self.tool_registry, self.permissions, self.confirmations, self.agent_audit
        )
        self.agent_executor.owner_policy = self.owner_policy
        from ..personal.controller import PersonalController
        self.personal = PersonalController(self)
        self.connect.attach_sync(self.personal.records)
        self.connect.sync.changed = self.sync_personal_changed
        from ..mail.controller import MailController
        self.mail = MailController(self)
        self.model_router = ModelRouter(self.model_registry, lambda: self.settings.get("model_policy", {}),
                                        self.model_benchmarks, self.model_residency)
        from .model_controller import ModelController
        self.models = ModelController(self)
        from .desktop_controller import DesktopController
        self.desktop = DesktopController(self)
        planner = CompositePlanner(
            DeterministicPlanner(),
            WorkspacePlanner(self.workspace_repo),
            StructuredCodingPlanner(
                self.ollama, self.model_router, self.workspace_repo, self.repository_maps, self.code_retrieval
            ),
        )
        self.agent_orchestrator = AgentOrchestrator(
            planner, self.agent_executor, self.agent_task_repo, max_iterations=12
        )

        self.chats = self.chat_repo.load_all()
        if not self.chats:
            chat = Chat(title="First Conversation", preset="normal")
            self.chats[chat.id] = chat
        self.model_infos = []
        from ..services.presets import PresetCatalog
        self.presets = PresetCatalog(self)
        from ..connect.inference_client import RemoteInferenceClient
        self.remote_inference = RemoteInferenceClient(self.connect)
        self.current_chat_id = max(self.chats.values(), key=lambda chat: chat.updated_at).id
        self.ollama_state = "Checking Ollama"
        from .chat_controller import ChatController
        from .agent_controller import AgentController
        from .knowledge_controller import KnowledgeController
        from .data_controller import DataController
        from .studio_controller import StudioController

        self.chat = ChatController(self)
        self.connect.sync.store.attach_chat(self.chat_repo, live=lambda: self.chats,
            busy=lambda: set(self.chat.generations), publish=self.sync_chat_changed)
        self.agent = AgentController(self)
        self.knowledge = KnowledgeController(self)
        self.mail.composition.restore_knowledge_sources()
        self.data = DataController(self)
        self.studio = StudioController(self)
        from .coding_workflow import CodingWorkflow
        self.coding = CodingWorkflow(self)
        from ..services.discord_transport import DiscordTransport
        from .communication_tool import CommunicationSubmitTool
        self.discord_transport = DiscordTransport(data)
        self.tool_registry.register(CommunicationSubmitTool(self))
        from ..studio_tooling.controller import StudioToolingController
        self.studio_tooling = StudioToolingController(self)
        from ..services.media_service import MediaService
        self.media = MediaService(self)
        from .research_controller import ResearchController

        self.research = ResearchController(self)
        from ..interaction.orchestrator import NaturalLanguageOrchestrator
        self.interaction = NaturalLanguageOrchestrator(self)
        self.closing = False
        self.restart_required = False

    async def dispatch(self, operation, arguments):
        if self.closing:
            raise RuntimeError("OLIVE is shutting down")
        if self.restart_required and operation not in {"data.status", "data.diagnostics"}:
            raise RuntimeError("Restore succeeded. Restart OLIVE before making further changes.")
        group, name = operation.split(".", 1)
        if group not in {"chat", "agent", "knowledge", "data", "studio", "research", "models", "desktop", "interaction"} or name.startswith("_"):
            raise ValueError("Unknown application operation")
        if group == "interaction" and name not in {"submit", "cancel", "select_workspace", "edit_draft", "inspect", "presentation_context", "clear_context"}:
            raise ValueError("Unknown interaction operation")
        method = getattr(getattr(self, group), name)
        result = method(**arguments)
        if inspect.isawaitable(result):
            result = await result
        return deepcopy(result)

    def publish(self, topic, value):
        self.emit(topic, deepcopy(value))

    def sync_personal_changed(self):
        self.personal.scheduler.changed()
        for domain in ('tasks', 'calendar', 'reminders'):
            self.publish('personal.changed', {'domain': domain})

    def sync_chat_changed(self):
        if self.current_chat_id not in self.chats:
            if not self.chats:
                chat = Chat(title="New Chat")
                self.chats[chat.id] = chat
                self.chat_repo.save_all(self.chats.values())
            self.current_chat_id = next(iter(self.chats))
        self.publish("chats", self.chat.list())

    def save_chats(self):
        self.chat_repo.save_all(self.chats.values())
        self.publish("chats", self.chat.list())

    async def initialize(self):
        import asyncio
        from ..services.remote_inference_runtime import RemoteInferenceRuntime
        from ..connect.studio_runtime import StudioRuntime
        self.connect.attach_studio(StudioRuntime(self), asyncio.get_running_loop())
        self.connect.attach_inference(RemoteInferenceRuntime(self.presets, self.ollama), asyncio.get_running_loop())
        from concurrent.futures import Future
        import threading
        loop = asyncio.get_running_loop()
        owner = threading.get_ident()
        def dispatch_sync(action):
            if threading.get_ident() == owner:
                return action()
            future = Future()
            def run():
                if not future.set_running_or_notify_cancel():
                    return
                try:
                    future.set_result(action())
                except BaseException as error:
                    future.set_exception(error)
            loop.call_soon_threadsafe(run)
            try:
                return future.result(timeout=4)
            except TimeoutError:
                future.cancel()
                raise
        self.connect.sync.dispatch = dispatch_sync
        self.personal.scheduler.start()
        self.mail.background.start()
        try:
            await self.local_ollama_runtime.start()
            await self.model_registry.refresh()
            self.model_infos = await self.ollama.list_models()
            embedding = self.model_registry.select_embedding_model(self.settings.get("embedding_model"))
            if embedding:
                self.settings["embedding_model"] = embedding
                self.rag.embedding_model = embedding
                self.code_retrieval.embedding_model = embedding
                self.settings_repo.save(self.settings)
            default = choose_default_chat_model(
                [model for model in self.model_infos if not model.is_embedding]
            )
            for chat in self.chats.values():
                if chat.preset:
                    self.presets.apply(chat, chat.preset)
                elif not chat.model:
                    chat.model = default
            self.ollama_state = "Ollama ready" if self.model_infos else "Ollama ready. No models installed"
            self.save_chats()
        except Exception:
            logger.exception("Ollama initialization failed")
            self.ollama_state = "Ollama unavailable. Start Ollama and refresh Models"
        self.publish("models", self.data.models())
        self.publish("status", self.data.status())
        self.publish("desktop", self.desktop.status())
        await self.knowledge.resume_pending()

    async def _execute_indexing_job(self, job):
        await self.knowledge.execute_job(job)

    async def shutdown(self):
        try:
            if self.connect.inference is not None:
                await self.connect.inference.shutdown()
            if self.connect.studio is not None:
                await self.connect.studio.shutdown()
            await self.media.shutdown()
            self.closing = True
            await self.personal.close()
            await self.mail.close()
            await self.interaction.shutdown()
            self.model_benchmarks.cancel()
            await self.desktop.shutdown()
            await self.research.shutdown()
            self.chat.stop_all()
            self.agent.cancel()
            self.agent.cancel_tools()
            await self.indexing_scheduler.shutdown()
            await self.studio_tooling.shutdown()
            for session_id in list(self.run_service.sessions):
                await self.run_service.stop(session_id)
            if not self.restart_required:
                self.save_chats()
        finally:
            await asyncio.to_thread(self.connect.close)
            await self.local_ollama_runtime.close()
