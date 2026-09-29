import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse


class ApplicationControllerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.events = []
        self.approve = True

        async def confirm(request):
            return ConfirmationResponse(self.approve)

        self.s = ServiceContainer(
            lambda topic, value: self.events.append((topic, value)),
            confirm,
            self.root / "data",
            migrate=False,
        )
        self.chat_id = self.s.current_chat_id
        self.s.chats[self.chat_id].preset = ""  # Explicit fixture provider, independent of presets.

    async def asyncTearDown(self):
        await self.s.shutdown()
        self.temp.cleanup()

    def test_shared_graph_has_no_ui_dependency(self):
        self.assertIs(self.s.chat_service.ollama, self.s.ollama)
        self.assertIs(self.s.chat_service.rag, self.s.rag)
        self.assertIs(self.s.studio.s, self.s.agent.s)
        self.assertTrue(self.s.rag_store.path.is_relative_to(self.root))

    async def test_send_waits_for_in_flight_indexing_but_not_for_a_failed_job(self):
        import asyncio
        from olive.models import DocumentRef
        chat = self.s.chats[self.chat_id]
        ref = DocumentRef(id="doc-1", name="report.pdf", indexed=False, temporary=True)
        chat.documents.append(ref)
        job = self.s.indexing_jobs.enqueue(chat.id, ref.id, ref.name, "index", "v1")
        self.s.indexing_jobs.transition(job.id, "running", progress=10)
        async def finish():
            await asyncio.sleep(.3)
            ref.indexed = True
            self.s.indexing_jobs.transition(job.id, "completed", progress=100)
        asyncio.get_running_loop().create_task(finish())
        await self.s.chat._await_indexing(chat, timeout=5)
        self.assertTrue(ref.indexed)
        failed = DocumentRef(id="doc-2", name="broken.pdf", indexed=False, temporary=True)
        chat.documents.append(failed)
        other = self.s.indexing_jobs.enqueue(chat.id, failed.id, failed.name, "index", "v1")
        self.s.indexing_jobs.transition(other.id, "failed", error="unreadable")
        started = asyncio.get_running_loop().time()
        await self.s.chat._await_indexing(chat, timeout=5)
        self.assertLess(asyncio.get_running_loop().time() - started, 1)

    def test_new_chat_is_first_even_after_leaving_chat_saves_its_draft(self):
        from olive.bridge.chat_routes import search
        older = self.chat_id
        self.s.chats[older].add_message("user", "hello")
        created = self.s.chat.new()["id"]
        # Navigating away flushes the previous chat's unsent text in the same second.
        self.s.chat.save_draft(older, "half-typed thought")
        self.assertEqual(self.s.chat.list()[0]["id"], created)
        self.assertEqual(search(self.s, "")[0]["id"], created)
        self.assertEqual(self.s.chats[older].draft, "half-typed thought")

    async def test_wait_withdraws_pending_send_confirmation_and_keeps_draft(self):
        from unittest.mock import AsyncMock
        context = self.s.interaction.context(self.chat_id)
        context.pending = {"id": "draft", "type": "communication", "state": "awaiting_confirmation",
                           "entities": {"recipient": "John", "message": "hello"}}
        pending = asyncio.create_task(asyncio.sleep(60))
        self.s.interaction.active[self.chat_id] = pending
        gate = self.s.interaction.gates[self.chat_id] = asyncio.Event()
        gate.set()
        self.s.interaction.interpreter.interpret = AsyncMock(return_value={"confidence": 1, "clarification": "",
            "steps": [{"intent": "task.pause", "entities": {}, "references": {}}]})
        try:
            await self.s.interaction.submit("Wait", self.chat_id)
            await asyncio.gather(pending, return_exceptions=True)
            self.assertTrue(pending.cancelled())
            self.assertEqual(context.pending["id"], "draft")
            self.assertEqual(context.pending["state"], "prepared")
        finally:
            self.s.interaction.active.pop(self.chat_id, None)
            self.s.interaction.gates.pop(self.chat_id, None)

    def test_developer_inspector_returns_copies_and_never_grants_permission(self):
        context = self.s.interaction.context(self.chat_id)
        context.last_interpretation = {"steps": [{"intent": "application.launch"}]}
        before = self.s.permissions.policies()
        details = self.s.interaction.inspect(self.chat_id)
        details["interpretation"]["steps"].clear()
        self.assertTrue(context.last_interpretation["steps"])
        self.assertEqual(self.s.permissions.policies(), before)

    def test_draft_editor_preserves_destination_and_cannot_approve_send(self):
        context = self.s.interaction.context(self.chat_id)
        context.pending = {"type": "communication", "state": "prepared", "entities": {
            "application": "Example", "server": "Cedar", "channel": "news", "message": "hello"}}
        self.s.interaction.edit_draft(self.chat_id, message="hello everyone")
        self.assertEqual(context.pending["entities"], {
            "application": "Example", "server": "Cedar", "channel": "news", "message": "hello everyone"})
        self.assertEqual(context.pending["state"], "prepared")
        snapshot = self.s.chat.get(self.chat_id)
        snapshot["pending_draft"]["entities"]["channel"] = "changed"
        self.assertEqual(context.pending["entities"]["channel"], "news")
        self.s.interaction.edit_draft(self.chat_id, cancel=True)
        self.assertIsNone(context.pending)

    async def test_run_reserves_workspace_while_confirmation_is_pending(self):
        folder = self.root / "run-workspace"
        folder.mkdir()
        workspace = self.s.data.create_workspace("Run", str(folder))
        entered = asyncio.Event()
        release = asyncio.Event()

        async def pending_tool(*args, **kwargs):
            entered.set()
            await release.wait()
            raise PermissionError("Denied by fixture")

        self.s.agent.tool = pending_tool
        first = asyncio.create_task(self.s.studio.run(workspace["id"]))
        await entered.wait()
        with self.assertRaisesRegex(ValueError, "already has"):
            await self.s.studio.run(workspace["id"])
        release.set()
        with self.assertRaises(PermissionError):
            await first
        self.assertFalse(self.s.studio.launching)

    async def test_chat_stream_persists_sources_and_survives_selection(self):
        self.s.chats[self.chat_id].model = "fixture"

        async def reply(*args, **kwargs):
            async def stream():
                yield "Hello "
                await asyncio.sleep(0.06)
                yield "world"

            return stream(), SimpleNamespace(rag_results=[], memories=[])

        self.s.chat_service.stream_reply = reply
        generation = asyncio.create_task(self.s.chat.send(self.chat_id, "test"))
        await asyncio.sleep(0.01)
        other = self.s.chat.new()
        await generation
        restored = self.s.chat_repo.load_all()
        self.assertEqual(restored[self.chat_id].messages[-1].content, "Hello world")
        self.assertEqual(restored[self.chat_id].messages[-1].completion_state, "complete")
        self.assertEqual(restored[other["id"]].messages, [])
        self.assertTrue(any(topic == "chat_stream" for topic, _ in self.events))

    async def test_stop_generation_persists_partial_answer(self):
        self.s.chats[self.chat_id].model = "fixture"

        async def reply(*args, **kwargs):
            async def stream():
                yield "Partial"
                await asyncio.sleep(30)

            return stream(), SimpleNamespace(rag_results=[], memories=[])

        self.s.chat_service.stream_reply = reply
        task = asyncio.create_task(self.s.chat.send(self.chat_id, "test"))
        await asyncio.sleep(0.02)
        self.s.chat.stop(self.chat_id)
        await task
        self.assertFalse(self.s.chat.generations)
        self.assertEqual(self.s.chats[self.chat_id].messages[-1].content, "Partial")

    async def test_stream_failure_preserves_request_and_partial_without_action(self):
        self.s.chats[self.chat_id].model = "fixture"

        async def reply(*args, **kwargs):
            async def stream():
                yield "Partial code"
                raise RuntimeError("The response reached the model output limit")
            return stream(), SimpleNamespace(rag_results=[], memories=[])

        self.s.chat_service.stream_reply = reply
        with self.assertRaisesRegex(RuntimeError, "output limit"):
            await self.s.interaction.submit("Show me a script", self.chat_id)
        restored = self.s.chat_repo.load_all()[self.chat_id]
        self.assertEqual([m.content for m in restored.messages], ["Show me a script", "Partial code"])
        self.assertEqual(restored.messages[-1].completion_state, "incomplete")
        self.assertFalse(self.s.chat.generations)
        self.assertFalse(self.s.agent_task_repo.load_all())
        self.assertFalse(self.s.workspace_repo.load_all())
        self.assertFalse(self.s.run_service.sessions)

    async def test_studio_denial_and_hash_checked_save(self):
        workspace_dir = self.root / "workspace"
        workspace_dir.mkdir()
        path = workspace_dir / "a.py"
        path.write_text("one", encoding="utf-8")
        workspace = self.s.data.create_workspace("Test", str(workspace_dir))
        self.approve = False
        with self.assertRaises(PermissionError):
            await self.s.studio.access(workspace["id"], "open", path="a.py")
        self.approve = True
        opened = await self.s.studio.access(workspace["id"], "open", path="a.py")
        await self.s.studio.access(
            workspace["id"], "save", path="a.py", text="two", expected_hash=opened["loaded_hash"]
        )
        self.assertEqual(path.read_text(), "two")
        path.write_text("human", encoding="utf-8")
        state = self.s.studio.service(workspace["id"]).open_files["a.py"]
        with self.assertRaises(PermissionError):
            await self.s.studio.access(
                workspace["id"], "save", path="a.py", text="three", expected_hash=state.loaded_hash
            )
        self.assertEqual(path.read_text(), "human")
        self.assertTrue(self.s.agent.actions())

    async def test_studio_cannot_open_outside_approved_workspace(self):
        folder = self.root / "workspace"
        folder.mkdir()
        (self.root / "outside.txt").write_text("private")
        workspace = self.s.data.create_workspace("Test", str(folder))
        with self.assertRaises(PermissionError):
            await self.s.studio.access(workspace["id"], "open", path="../outside.txt")

    async def test_knowledge_ingestion_jobs_retrieval_and_removal(self):
        path = self.root / "source.txt"
        path.write_text("OLIVE uses local models and preserves private knowledge.", encoding="utf-8")

        async def no_models():
            return []

        self.s.ollama.list_models = no_models
        values = await self.s.knowledge.attach(self.chat_id, [str(path)], True)
        self.assertEqual(len(values), 1)
        self.assertTrue(values[0]["indexed"])
        self.assertEqual(Path(values[0]["original_path"]), path)
        self.assertEqual(self.s.knowledge.jobs()[0]["state"], "completed")
        self.assertTrue(Path(values[0]["stored_path"]).is_relative_to(self.root))
        self.s.knowledge.remove(self.chat_id, values[0]["id"])
        self.assertEqual(self.s.knowledge.list(), [])
        self.assertTrue(path.exists())

    def test_settings_invalid_input_does_not_mutate_chat(self):
        before = self.s.data.settings()
        settings = dict(before["settings"])
        settings["rag_semantic_weight"] = -5
        with self.assertRaises(ValueError):
            self.s.data.save_settings(self.chat_id, settings, before["params"], "Changed")
        self.assertEqual(self.s.data.settings(), before)

    def test_memory_and_project_roundtrip(self):
        self.s.data.memory_save("Remember the project uses local inference", "project")
        project = self.s.data.create_project("Example")
        self.s.chat.update(self.chat_id, project_id=project["id"])
        self.assertEqual(len(self.s.data.project_detail(project["id"])["Chats"]), 1)
        self.assertEqual(len(self.s.data.memories()), 1)

    async def test_restore_does_not_overwrite_restored_chats_on_shutdown(self):
        self.s.chat.update(self.chat_id, title="Before backup")
        path = self.s.data.backup()
        self.s.chat.update(self.chat_id, title="After backup")
        await self.s.data.restore(path, confirmed=True)
        await self.s.shutdown()
        self.assertEqual(self.s.chat_repo.load_all()[self.chat_id].title, "Before backup")

    async def test_regeneration_retains_prior_branch_and_cancellation_restores_it(self):
        chat = self.s.chats[self.chat_id]
        chat.model = "fixture"
        chat.add_message("user", "question")
        chat.add_message("assistant", "original")

        async def reply(*args, **kwargs):
            async def stream():
                yield "alternative"

            return stream(), SimpleNamespace(rag_results=[], memories=[])

        self.s.chat_service.stream_reply = reply
        await self.s.chat.send(self.chat_id, regenerate=True)
        self.assertEqual(chat.response_branches["0"], ["original", "alternative"])
        self.s.chat.branch(self.chat_id, 0)
        self.assertEqual(chat.messages[-1].content, "original")

    async def test_image_requires_vision_and_failed_request_is_preserved(self):
        chat = self.s.chats[self.chat_id]
        chat.model = "fixture"
        self.s.chat.images[chat.id] = [("image.png", "fixture")]

        async def no_vision(model):
            return False

        self.s.ollama.is_vision_model = no_vision
        with self.assertRaises(ValueError):
            await self.s.chat.send(chat.id, "describe")
        self.assertEqual([(m.role, m.content) for m in chat.messages], [("user", "describe")])

    async def test_model_download_requires_confirmation_and_is_not_automatic(self):
        from unittest.mock import AsyncMock

        self.s.ollama.pull = AsyncMock()
        with self.assertRaises(PermissionError):
            await self.s.data.pull_model("fixture")
        self.s.ollama.pull.assert_not_called()

    def test_memory_suggestion_review_and_rejection(self):
        suggestion = self.s.memory_suggestions.suggest("I prefer concise replies", self.chat_id, 0)[0]
        self.s.chat.suggestions[suggestion.id] = suggestion
        self.s.data.review_suggestion(suggestion.id, approve=False)
        self.assertEqual(self.s.data.memories(), [])
        self.s.chat.suggestions[suggestion.id] = suggestion
        self.s.data.review_suggestion(suggestion.id, approve=True)
        self.assertEqual(self.s.data.memories()[0]["content"], "I prefer concise replies")

    def test_settings_roundtrip_preserves_unknown_legacy_fields(self):
        snapshot = self.s.data.settings()
        snapshot["settings"]["preserved_legacy_option"] = "keep"
        snapshot["settings"]["theme"] = "Light"
        self.s.data.save_settings(
            self.chat_id, snapshot["settings"], snapshot["params"], snapshot["system_prompt"], "Local model"
        )
        self.assertEqual(self.s.settings_repo.load()["preserved_legacy_option"], "keep")
        self.assertEqual(self.s.settings_repo.load()["theme"], "Light")

    async def test_recovered_task_resume_does_not_repeat_completed_steps(self):
        from olive.agent.agent_task import AgentTask, AgentStep
        from olive.agent.tool_result import ToolResult
        from unittest.mock import AsyncMock

        task = AgentTask(
            "saved objective",
            state="paused",
            plan=[
                AgentStep("already done", "fixture.done", {}, state="completed"),
                AgentStep("pending", "fixture.next", {}),
            ],
        )
        self.s.agent_task_repo.save(task)
        self.s.agent_executor.execute = AsyncMock(return_value=ToolResult(True, "done"))
        result = await self.s.agent.resume(task.id)
        self.assertEqual(result["state"], "completed")
        self.assertEqual(self.s.agent_executor.execute.await_count, 1)


if __name__ == "__main__":
    unittest.main()


class OllamaStatusWordingTests(unittest.IsolatedAsyncioTestCase):
    """Status text shown in the activity centre must be readable, not mis-encoded."""

    async def test_unavailable_status_is_plain_readable_text(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)

        async def confirm(request):
            return ConfirmationResponse(True)

        s = ServiceContainer(lambda topic, value: None, confirm, Path(temp.name) / "data", migrate=False)
        self.addAsyncCleanup(s.shutdown)

        async def failing_refresh():
            raise ConnectionError("Ollama unavailable")

        s.model_registry.refresh = failing_refresh
        await s.initialize()
        self.assertEqual(s.ollama_state, "Ollama unavailable. Start Ollama and refresh Models")
        self.assertNotIn("?", s.ollama_state)
        self.assertEqual(s.data.status()["ollama"], s.ollama_state)
