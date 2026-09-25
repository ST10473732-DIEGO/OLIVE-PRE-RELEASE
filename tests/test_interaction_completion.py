"""Execution regressions for generic 3.4.1 capability connections."""

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock

from olive.interaction.context import InteractionContext
from olive.interaction.router import CapabilityRouter


class CompletionTests(unittest.IsolatedAsyncioTestCase):
    async def test_return_to_context_browser_reuses_verified_tab_and_retains_file(self):
        desktop = SimpleNamespace(browser_tab=AsyncMock(return_value={"tab_id": "known-tab"}),
                                  discover_applications=AsyncMock())
        router = CapabilityRouter(SimpleNamespace(desktop=desktop))
        context = InteractionContext(tab_id="known-tab", browser_application="Chrome",
                                     entities={"application": "Notes", "path": "selected.pdf"})
        for intent in ("application.launch", "application.activate"):
            step = {"intent": intent, "entities": {"application": "Chrome"}, "references": {}}
            await router.execute(step, context)
            context.accept(step)
        self.assertEqual(context.entities["path"], "selected.pdf")
        self.assertEqual(context.tab_id, "known-tab")
        desktop.discover_applications.assert_not_awaited()
        desktop.browser_tab.assert_awaited_with("switch_tab", tab_id="known-tab")
        desktop.browser_tab.return_value = {"tab_id": "different-tab"}
        with self.assertRaisesRegex(ValueError, "verified"):
            await router.execute(step, context)

    async def test_compound_document_answer_reads_resolved_file_through_guarded_rag(self):
        async def reply():
            yield "The selected report "
            yield "describes the project [report.pdf]."
        path = str(Path.cwd() / "report.pdf")
        services = SimpleNamespace(desktop=SimpleNamespace(), agent=SimpleNamespace(tool=AsyncMock(return_value={"document_id": "doc-one"})),
            chats={"chat": SimpleNamespace(model="local-model")},
            chat_service=SimpleNamespace(stream_reply=AsyncMock(return_value=(reply(), None))))
        result = await CapabilityRouter(services).execute({"intent": "knowledge.query",
            "entities": {"path": path, "query": "What project does this describe?"}, "references": {}},
            InteractionContext(chat_id="chat"))
        self.assertIn("[report.pdf]", result)
        self.assertEqual(services.agent.tool.await_args.args[0], "knowledge.read_selected")
        self.assertEqual(services.agent.tool.await_args.args[1]["path"], path)
        self.assertEqual(services.chat_service.stream_reply.await_args.kwargs["selected_document_id"], "doc-one")
        services.agent.tool.side_effect = PermissionError("Read denied")
        services.chat_service.stream_reply.reset_mock()
        with self.assertRaises(PermissionError):
            await CapabilityRouter(services).execute({"intent": "knowledge.query", "entities": {"path": path},
                "references": {}}, InteractionContext(chat_id="chat"))
        services.chat_service.stream_reply.assert_not_awaited()

    async def test_browser_draft_preparation_never_submits_or_overwrites_another_draft(self):
        import json
        from olive.interaction.browser_communication import prepare_browser_draft
        controls = [{"id": key, "name": key, "type": "text", "enabled": True} for key in ("to", "subject", "body")]
        controls.append({"id": "standalone", "name": "Message", "type": "text", "enabled": True})
        controls[2].update(type="", tag="textarea")
        desktop = SimpleNamespace(browser_observe=AsyncMock(return_value={"url": "https://example.test", "controls": controls}),
            browser=SimpleNamespace(execute=AsyncMock(return_value="")), browser_action=AsyncMock(return_value={"verified": True}),
            browser_send=AsyncMock())
        services = SimpleNamespace(desktop=desktop, model_router=SimpleNamespace(route=lambda _: SimpleNamespace(name="qwen3:8b")),
            ollama=SimpleNamespace(chat_measured=AsyncMock(return_value={"content": json.dumps(
                {"recipient": "to", "subject": "subject", "message": "body"})})))
        pending = {"entities": {"recipient": "alex@example.test", "subject": "Review", "message": "Hello"}}
        await prepare_browser_draft(services, pending, InteractionContext(tab_id="tab"))
        self.assertEqual([call.kwargs["value"] for call in desktop.browser_action.await_args_list],
                         ["alex@example.test", "Review", "Hello"])
        desktop.browser_send.assert_not_awaited()
        self.assertEqual(services.ollama.chat_measured.await_args.kwargs["format"]["properties"]["message"], {"enum": ["body"]})
        desktop.browser_action.reset_mock()
        desktop.browser.execute.return_value = "Existing private draft"
        with self.assertRaisesRegex(ValueError, "different draft"):
            await prepare_browser_draft(services, pending, InteractionContext(tab_id="tab"))
        desktop.browser_action.assert_not_awaited()
        services.ollama.chat_measured.return_value = {"content": json.dumps(
            {"recipient": "to", "subject": "subject", "message": "standalone"})}
        with self.assertRaisesRegex(ValueError, "separate recipient"):
            await prepare_browser_draft(services, pending, InteractionContext(tab_id="tab"))
        desktop.browser_action.assert_not_awaited()

    def test_copy_checks_source_read_and_destination_write(self):
        from olive.agent.executor import _target_for_permission
        arguments = {"path": "source.pdf", "destination": "copied.pdf", "workspace": str(Path.cwd())}
        self.assertEqual(_target_for_permission("filesystem.read", arguments), str(Path.cwd() / "source.pdf"))
        self.assertEqual(_target_for_permission("filesystem.write", arguments), str(Path.cwd() / "copied.pdf"))

    def test_local_python_fallback_avoids_windows_store_alias(self):
        import sys
        from olive.services.build_test_service import BuildAndTestService
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(BuildAndTestService.python_executable(Path(directory)), getattr(sys, "_base_executable", sys.executable) if sys.platform == "linux" else sys.executable)

    def test_morning_search_uses_local_noon_and_downloaded_proxy_is_explicit(self):
        from olive.interaction.file_intent import constraints
        result = constraints({"name": "", "name_match": "any", "extension": "pdf", "location": "Downloads",
            "time": "this_morning", "absolute_date": "", "timestamp": "downloaded", "recency": "all"}, "2026-09-09")
        self.assertEqual(result["date"], "2026-09-09")
        self.assertEqual(result["time_until"], "12:00")
        self.assertEqual(result["time_basis"], "downloaded")

    async def test_project_document_link_preserves_source_and_existing_project_data(self):
        from olive.application.service_container import ServiceContainer
        from olive.agent.confirmation_service import ConfirmationResponse
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            services = ServiceContainer(lambda *args: None, AsyncMock(return_value=ConfirmationResponse(False)), root / "data", migrate=False)
            try:
                source = root / "notes.txt"
                source.write_text("Project management notes for the university course", encoding="utf-8")
                services.ollama.is_model_available = AsyncMock(return_value=False)
                project = services.data.create_project("University")
                context = services.interaction.context(services.current_chat_id)
                step = {"intent": "project.add_file", "entities": {"path": str(source), "project": "University"}}
                with self.assertRaises(PermissionError):
                    await services.interaction.router.execute(step, context)
                self.assertEqual(services.project_repo.load_all()[project["id"]].knowledge_ids, [])
                services.permissions.save({"filesystem.read": "allow", "knowledge.write": "allow"})
                await services.interaction.router.execute(step, context)
                self.assertTrue(source.exists())
                saved = services.project_repo.load_all()[project["id"]]
                self.assertEqual(len(saved.knowledge_ids), 1)
                self.assertEqual(len(services.data.project_detail(saved.id)["Knowledge"]), 1)
                self.assertEqual(services.chats[context.chat_id].project_id, None)
            finally:
                await services.shutdown()

    async def test_indexed_topic_search_excludes_outside_and_denied_documents(self):
        from unittest.mock import Mock
        from olive.interaction.indexed_files import IndexedFileSearchTool
        from olive.agent.permission_service import PermissionDecision
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            refs = [SimpleNamespace(id=name, original_path=str(root / path), indexed=True) for name, path in
                    [("allowed", "docs/report.pdf"), ("denied", "docs/private.pdf"), ("outside", "elsewhere/report.pdf")]]
            store = SimpleNamespace(lexical_search=Mock(return_value=[(SimpleNamespace(document_id="allowed"), 1)]))
            services = SimpleNamespace(chats={"chat": SimpleNamespace(id="chat", documents=refs)}, rag=SimpleNamespace(store=store),
                permissions=SimpleNamespace(evaluate=lambda permission, path: SimpleNamespace(
                    decision=PermissionDecision.DENY if path.endswith("private.pdf") else PermissionDecision.ALLOW)))
            result = await IndexedFileSearchTool(services).execute({"path": str(root / "docs"), "chat_id": "chat", "query": "management"}, None)
            self.assertEqual([Path(p) for p in result.data["paths"]], [root / "docs/report.pdf"])
            store.lexical_search.assert_called_once_with("chat", "management", 60, ["allowed"])

    def test_scoped_lexical_search_filters_before_limit(self):
        from olive.storage.rag_store import RAGStore
        with tempfile.TemporaryDirectory() as directory:
            store = RAGStore(Path(directory) / "rag.sqlite")
            for name in ("allowed", "outside"):
                store.replace_document(name, "chat", name, "pdf", 1, None, [
                    {"chat_id": "chat", "document_name": name, "chunk_index": 0, "page_number": 1, "content": "project management"}])
            hits = store.lexical_search("chat", "project management", 1, ["allowed"])
            self.assertEqual([hit.document_id for hit, _ in hits], ["allowed"])
            self.assertEqual(store.lexical_search("chat", "project", 1, []), [])

    async def test_attachment_preserves_file_across_app_switch_and_obeys_denial(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "report.pdf")
            context = InteractionContext(tab_id="browser", entities={"application": "Editor", "path": path})
            context.accept({"intent": "application.launch", "entities": {"application": "Chrome"}})
            desktop = SimpleNamespace(
                browser_observe=AsyncMock(return_value={"controls": [
                    {"id": "upload", "type": "file", "enabled": True}]}),
                browser_upload=AsyncMock(side_effect=PermissionError("Upload denied")))
            router = CapabilityRouter(SimpleNamespace(desktop=desktop))
            step = context.resolve({"intent": "communication.attach", "entities": {}, "references": {"path": "path"}})
            with self.assertRaises(PermissionError):
                await router.execute(step, context)
            desktop.browser_upload.assert_awaited_once_with("upload", path)
            self.assertEqual(context.entities["path"], path)

    async def test_ambiguous_upload_fields_never_upload(self):
        desktop = SimpleNamespace(browser_observe=AsyncMock(return_value={"controls": [
            {"id": str(i), "type": "file", "enabled": True} for i in range(2)]}), browser_upload=AsyncMock())
        router = CapabilityRouter(SimpleNamespace(desktop=desktop))
        context = InteractionContext(tab_id="tab", entities={"path": str(Path.cwd() / "report.pdf")})
        with self.assertRaisesRegex(ValueError, "Which attachment"):
            await router.execute({"intent": "communication.attach", "entities": {}}, context)
        desktop.browser_upload.assert_not_awaited()

    async def test_media_skip_requires_verified_completion(self):
        desktop = SimpleNamespace(media_sessions=AsyncMock(return_value=[{"application_id": "Player"}]),
                                  media_action=AsyncMock(return_value={"verified": False}))
        router = CapabilityRouter(SimpleNamespace(desktop=desktop))
        context = InteractionContext()
        with self.assertRaisesRegex(ValueError, "not confirmed"):
            await router.execute({"intent": "media.next", "entities": {}}, context)
        desktop.media_action.return_value = {"verified": True}
        self.assertIn("previous", await router.execute({"intent": "media.previous", "entities": {}}, context))
        self.assertEqual(context.media_application, "Player")

    async def test_move_updates_selected_file_and_copy_retains_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = str(Path(directory) / "report.pdf")
            destination = str(Path(directory) / "Documents")
            # Stat answers per path: the source is a file, the destination a folder.
            agent = SimpleNamespace(tool=AsyncMock(side_effect=lambda name, args, reason: {
                "is_directory": args.get("path") == destination} if name == "filesystem.stat" else {}))
            router = CapabilityRouter(SimpleNamespace(desktop=None, agent=agent))
            for operation in ("copy", "move"):
                context = InteractionContext(entities={"path": source}, file_candidates=[source])
                step = {"intent": "filesystem." + operation, "entities": {"path": source, "destination": destination}}
                await router.execute(step, context)
                context.accept(step)
                expected = str(Path(destination) / "report.pdf")
                agent.tool.assert_awaited_with("filesystem." + operation, {"path": source, "destination": expected}, "Transfer the selected file")
                self.assertEqual(context.entities["path"], expected if operation == "move" else source)

    async def test_new_tab_keeps_selected_document(self):
        desktop = SimpleNamespace(browser=SimpleNamespace(provider=SimpleNamespace(pages={"old": object()})),
            browser_tab=AsyncMock(return_value=[{"id": "old"}, {"id": "new"}]))
        router = CapabilityRouter(SimpleNamespace(desktop=desktop))
        context = InteractionContext(tab_id="old", entities={"path": "selected.pdf"})
        await router.execute({"intent": "browser.interact", "entities": {"action": "new_tab"}}, context)
        self.assertEqual(context.tab_id, "new")
        self.assertEqual(context.entities["path"], "selected.pdf")
        desktop.browser_tab.assert_awaited_once_with("new_tab", url="about:blank")
