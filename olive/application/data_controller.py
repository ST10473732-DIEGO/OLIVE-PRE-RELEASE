"""Validated settings and local data operations shared across desktop windows."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

from ..identity import display_alias
from ..config import APP_VERSION, DEFAULT_SYSTEM_PROMPT, EMBEDDING_MODEL
from ..projects import Project
from ..services.ocr_service import OCRService
from ..services.rag_settings import validate_rag_settings


class DataController:
    def __init__(self, services):
        self.s = services

    def status(self):
        jobs = self.s.indexing_jobs.list_all()
        embedding = self.s.model_registry.get(self.s.rag.embedding_model)
        return {
            "version": APP_VERSION,
            "ollama": self.s.ollama_state,
            "agent": self.s.agent.current.state if self.s.agent.current else "Ready",
            "indexing": sum(job.state in {"queued", "running"} for job in jobs),
            "chat_models": len(self.models()),
            "embedding_available": bool(embedding and embedding.supports_embeddings),
        }

    def home(self):
        """Bounded real recents for presentation; never resume actions or invent activity."""
        chats = [c for c in sorted(self.s.chats.values(), key=lambda c: c.updated_at, reverse=True)
                 if c.messages or getattr(c, "draft", "")]
        recent = [{"key": c.id, "title": c.title, "subtitle": "Conversation", "feature": "chat",
                   "kind": "chat", "glyph": "chat"} for c in chats[:4]]
        for w in self.workspaces()[:2]:
            recent.append({"key": w["id"], "title": w["title"], "subtitle": "Workspace", "feature": "studio",
                           "kind": "workspace", "glyph": "studio"})
        return {"recent": recent[:6], "chat_id": self.s.current_chat_id, "status": self.status(),
                "context": self.s.interaction.presentation_context()}

    def models(self):
        return [
            {"name": model.name, "alias": display_alias(self.s.model_aliases.get(model.name, model.name))}
            for model in self.s.model_infos
            if not model.is_embedding
        ]

    async def refresh_models(self):
        await self.s.initialize()
        return self.models()

    async def pull_model(self, name, confirmed=False):
        if not confirmed:
            raise PermissionError("Model installation requires an explicit download confirmation")
        name = name.strip()
        if not name or len(name) > 160 or any(character.isspace() for character in name):
            raise ValueError("Enter a valid Ollama model name")
        await self.s.ollama.pull(name)
        return await self.refresh_models()

    def settings(self, chat_id=None):
        chat = self.s.chats[chat_id or self.s.current_chat_id]
        return {
            "settings": deepcopy(self.s.settings),
            "params": dict(chat.params),
            "system_prompt": chat.system_prompt,
            "model": chat.model,
            "alias": display_alias(self.s.model_aliases.get(chat.model, "")),
            "chat_id": chat.id,
        }

    def save_settings(self, chat_id, settings, params, system_prompt, alias=""):
        if chat_id in self.s.chat.generations:
            raise ValueError("Stop generation before changing conversation settings")
        values = deepcopy(self.s.settings)
        values.update(settings)
        from ..research.settings import ResearchSettings

        research_settings = ResearchSettings.validated(values.get("research", {}))
        if self.s.research.starting and research_settings != self.s.research.settings():
            raise ValueError("Pause Research before changing its settings")
        values["research"] = research_settings.to_dict()
        generation = dict(self.s.chats[chat_id].params)
        generation.update(params)
        validated = validate_rag_settings(
            generation["rag_top_k"],
            values["rag_lexical_weight"],
            values["rag_semantic_weight"],
            values["rag_minimum_score"],
        )
        generation["temperature"] = float(generation["temperature"])
        generation["top_p"] = float(generation["top_p"])
        generation["max_tokens"] = max(64, int(generation["max_tokens"]))
        generation["history_messages"] = max(0, int(generation["history_messages"]))
        if not 0 <= generation["temperature"] <= 2 or not 0 < generation["top_p"] <= 1:
            raise ValueError("Temperature or top-p outside supported range")
        generation["rag_top_k"] = validated["top_k"]
        values["max_indexing_workers"] = min(3, max(1, int(values["max_indexing_workers"])))
        configured = values.get("ocr_executable", "").strip()
        if configured:
            configured = OCRService.validate_executable(configured)
        values["ocr_executable"] = configured
        values["embedding_model"] = values.get("embedding_model", "").strip() or EMBEDDING_MODEL
        chat = self.s.chats[chat_id]
        chat.params = generation
        chat.system_prompt = system_prompt.strip() or DEFAULT_SYSTEM_PROMPT
        self.s.settings = values
        self.s.rag.embedding_model = values["embedding_model"]
        self.s.code_retrieval.embedding_model = values["embedding_model"]
        self.s.rag.lexical_weight = validated["lexical_weight"]
        self.s.rag.semantic_weight = validated["semantic_weight"]
        self.s.rag.minimum_score = validated["relevance_threshold"]
        self.s.indexing_scheduler.max_workers = values["max_indexing_workers"]
        self.s.documents.ocr = OCRService(configured or None)
        self.s.diagnostics.ocr = self.s.documents.ocr
        self.s.model_defaults[chat.model] = dict(generation)
        self.s.model_aliases[chat.model] = alias.strip()
        self.s.settings_repo.save(values)
        self.s.settings_repo.save_model_defaults(self.s.model_defaults)
        self.s.settings_repo.save_model_aliases(self.s.model_aliases)
        self.s.save_chats()
        self.s.publish("settings", self.settings(chat_id))
        return self.settings(chat_id)

    def projects(self):
        return [project.to_dict() for project in self.s.project_repo.load_all().values()]

    def create_project(self, title, description=""):
        if not title.strip():
            raise ValueError("Project title is required")
        project = Project(title.strip(), description)
        self.s.project_repo.save(project)
        self.s.publish("projects", self.projects())
        return project.to_dict()

    def create_coding_project(self, name, language):
        from ..services.project_scaffold import create_folder
        path = create_folder(self.s.data_dir, name, language)
        project = self.create_project(name)
        return self.create_workspace(name, str(path), project['id'])

    def project_detail(self, project_id):
        project = self.s.project_repo.load_all()[project_id]
        chats = [self.s.chat.get(chat.id) for chat in self.s.chats.values() if chat.project_id == project_id]
        from ..agent.permission_service import PermissionDecision
        native={}
        for name,domain,kind in [('Calendar','calendar','event'),('Personal Tasks','tasks','task')]:
            if self.s.permissions.evaluate(domain+'.read').decision==PermissionDecision.ALLOW:
                native[name]=self.s.personal.records.search(kind,project_id=project_id,limit=200)['items']
        if hasattr(self.s,'mail') and self.s.permissions.evaluate('mail.read').decision==PermissionDecision.ALLOW:
            native['Mail']=self.s.mail.local.search(project_id=project_id,limit=50)['items']
        return {
            **native,
            "Overview": project.to_dict(),
            "Chats": chats,
            "Knowledge": [dict(ref.to_dict(), chat_id=chat.id) for chat in self.s.chats.values() for ref in chat.documents
                          if chat.project_id == project_id or ref.id in project.knowledge_ids],
            "Web Knowledge": [source for source in self.s.research.web_sources() if source["project_id"] == project_id],
            "Workspace/Files": [w for w in self.workspaces() if w["project_id"] == project_id],
            "Tasks": [task for task in self.s.agent.history() if task["project_id"] == project_id],
            "Memories": [m for m in self.memories() if m["id"] in project.memory_ids],
            "Research": self.s.research.project_reports(project_id),
        }

    def workspaces(self):
        return [workspace.to_dict() for workspace in self.s.workspace_repo.load_all().values()]

    def create_workspace(self, title, path, project_id=None, trust_level="approved"):
        if trust_level not in {"trusted", "approved", "untrusted"}:
            raise ValueError("Invalid workspace trust")
        workspace = self.s.workspace_service.create(title or Path(path).name, path, project_id)
        workspace.trust_level = trust_level
        self.s.workspace_repo.save(workspace)
        self.s.publish("workspaces", self.workspaces())
        return workspace.to_dict()

    def memories(self, query="", category="All"):
        values = [m for m, _ in self.s.memory.search(query, 200, 0)] if query else self.s.memory.list_all()
        result = []
        for memory in values:
            if category != "All" and memory.category != category:
                continue
            value = memory.to_dict()
            source = self.s.chats.get(memory.source_chat_id)
            value["source_title"] = (
                source.title if source else ("Deleted conversation" if memory.source_chat_id else "Manual")
            )
            if source:
                message = next((m for m in source.messages if m.id == memory.source_message_id), None)
                value["source_excerpt"] = message.content[:200] if message else ""
                value["project_id"] = source.project_id
            result.append(value)
        return result

    def memory_save(self, content, category="manual", memory_id=None):
        if memory_id:
            self.s.memory.update(memory_id, content=content, category=category)
        else:
            self.s.memory.add(content, category)
        self.s.publish("memories", self.memories())
        return self.memories()

    def memory_delete(self, memory_id):
        self.s.memory.delete(memory_id)
        self.s.publish("memories", self.memories())
        return self.memories()

    def suggestions(self):
        return [asdict(value) for value in self.s.chat.suggestions.values()]

    def review_suggestion(self, suggestion_id, approve=False, content=None):
        suggestion = self.s.chat.suggestions[suggestion_id]
        if approve:
            if content is not None:
                suggestion.content = content.strip()
            self.s.memory_suggestions.approve(suggestion)
        del self.s.chat.suggestions[suggestion_id]
        return self.memories()

    def permissions(self):
        values = self.s.permissions.policies()
        values["permissions"] = dict(self.s.permissions.DEFAULTS, **values["permissions"])
        return values

    def save_permissions(self, permissions, scopes):
        for scope in scopes:
            if (
                scope.get("decision") not in {"allow", "ask", "deny"}
                or not (scope.get("application") or scope.get("path"))
                or (scope.get("path") and not Path(scope["path"]).is_absolute())
                or not isinstance(scope.get("application", ""), str)
                or len(scope.get("application", "")) > 160
                or scope.get("permission") not in self.s.permissions.DEFAULTS
            ):
                raise ValueError("Each scope needs an application or absolute folder, a known permission and a valid decision")
        self.s.permissions.save(permissions, scopes)
        return self.permissions()

    def clear_approvals(self):
        return self.s.permissions.clear_trusted_actions()

    async def diagnostics(self, chat_id=None):
        result = await self.s.diagnostics.collect(self.s.chats[chat_id or self.s.current_chat_id])
        result["docker_available"] = await asyncio.to_thread(self.s.run_service.providers.docker.available)
        result["native_execution"] = True
        result["active_agent"] = bool(self.s.agent.active)
        result["run_sessions"] = len(self.s.run_service.sessions)
        result.update(self.s.research.diagnostics())
        desktop = self.s.desktop
        result["desktop_control"] = {"enabled": desktop.configuration()["enabled"], "provider": desktop.provider.name,
            "active": desktop.operation is not None or desktop.universal.owner is not None, "emergency_stop": desktop.stop_event.is_set(),
            "capture_provider": "window-scoped Pillow/Win32", "interactive_browser": desktop.browser.provider.name,
            "browser_running": desktop.browser.provider.context is not None,
            "media_provider": desktop.media.provider.name,
            "media_connected": desktop.media.provider.manager is not None,
            "discovered_applications": len(desktop.discovery.applications),
            "unknown_app_policy": desktop.configuration()["unknown_app_policy"],
            "workflow_operations": len(desktop.universal.history),
            "screenshot_count": len(desktop.screenshots.records)}
        result["model_stack"] = self.s.models.status()
        result['mail']={'schema':self.s.mail.store.VERSION,'active_operations':len(self.s.mail.active),
            'connections':[{'id':c['id'],'enabled':c['enabled'],'state':c['state'],'sync':c.get('sync_status'),'test':c.get('test_status')} for c in self.s.mail.connections.list()['items']],
            'submission_states':[{k:r.get(k) for k in ('id','state','category','sent_copy_state')} for r in self.s.mail.submissions.list()['items']]}
        return result

    def maintenance(self):
        return self.s.maintenance.scan(self.s.chats)

    def backup(self, path=None):
        if self.s.mail.active or self.s.personal.active:
            raise ValueError('Wait for current Mail and Personal Core writes before creating a consistent backup')
        self.s.save_chats()
        return str(self.s.backups.create(Path(path) if path else None))

    async def restore(self, path, confirmed=False):
        if not confirmed:
            raise PermissionError("Restore requires confirmation")
        if (
            self.s.chat.generations
            or self.s.interaction.active
            or self.s.interaction.interpreting
            or self.s.agent.active
            or self.s.agent.tool_cancellations
            or self.s.studio.launching
            or self.s.studio.validation_cancellations
            or self.s.knowledge.upgrade_task
            or self.s.model_benchmarks.active
            or self.s.research.starting
            or self.s.desktop.operation
            or self.s.desktop.browser.provider.context is not None
            or any(job.state == "running" for job in self.s.indexing_jobs.list_all())
            or any(
                session.state in {"starting", "running"} for session in self.s.run_service.sessions.values()
            )
        ):
            raise ValueError("Stop active work before restoring")
        if self.s.personal.active:
            raise ValueError('Wait for personal data operations before restoring')
        if self.s.mail.active or self.s.mail.submissions.active or self.s.mail.sync.active or self.s.mail.pending_sends:
            raise ValueError('Wait for Mail operations before restoring')
        await self.s.personal.scheduler.close()
        await self.s.mail.background.close()
        try:
            safety = self.s.backups.restore(Path(path), confirmed=True)
        except BaseException:
            self.s.personal.scheduler.stopping = False
            self.s.personal.scheduler.start()
            self.s.mail.background.closed=False;self.s.mail.background.start()
            raise
        # Reload instead of allowing old in-memory chats to overwrite restored data on exit.
        self.s.chats = self.s.chat_repo.load_all()
        self.s.mail.composition.restore_knowledge_sources()
        if not self.s.chats:
            from ..models import Chat

            chat = Chat()
            self.s.chats[chat.id] = chat
        self.s.current_chat_id = next(iter(self.s.chats))
        self.s.publish("chats", self.s.chat.list())
        self.s.restart_required = True
        return f"Restore complete. Restart OLIVE to reload all services. Safety backup: {safety.name}"

    def export(self, path, kind="chat", chat_id=None):
        destination = Path(path)
        if kind == "memory":
            self.s.backups.export_memories(
                destination, [memory.to_dict() for memory in self.s.memory.list_all()]
            )
        elif destination.suffix.lower() == ".md":
            chat = self.s.chats[chat_id or self.s.current_chat_id]
            destination.write_text(
                f"# {chat.title}\n\n"
                + "\n\n".join(f"## {message.role.title()}\n\n{message.content}" for message in chat.messages),
                encoding="utf-8",
            )
        else:
            self.s.backups.export_chats(
                destination, [self.s.chats[chat_id or self.s.current_chat_id].to_dict()]
            )
        return str(destination)
