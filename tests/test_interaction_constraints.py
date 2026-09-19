import json
from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from pathlib import Path
import tempfile
import os

from olive.interaction.file_intent import constraints
from olive.interaction.context import InteractionContext
from olive.interaction.router import CapabilityRouter
from olive.interaction.pending_intent import pending_request


class ConstraintTests(unittest.IsolatedAsyncioTestCase):
    async def test_known_application_activation_is_bounded_and_other_operations_continue(self):
        from olive.interaction.application_intent import existing_application_request
        ollama = SimpleNamespace(chat_measured=AsyncMock(return_value={"content": '{"operation":"activate","application":"Chrome"}'}))
        router = SimpleNamespace(route=lambda _: SimpleNamespace(name="qwen3:8b", role="fast"))
        context = {"entities": {"application": "Example", "previous_application": "Chrome"}, "browser_application": "Chrome"}
        result = await existing_application_request(ollama, router, "Go back to Chrome", context)
        self.assertEqual(result["steps"], [{"intent": "application.launch", "entities": {"application": "Chrome"}, "references": {}}])
        ollama.chat_measured.return_value = {"content": '{"operation":"other","application":""}'}
        self.assertIsNone(await existing_application_request(ollama, router, "Open Chrome and search for birds", context))
        ollama.chat_measured.return_value = {"content": '{"operation":"activate","application":"Invented"}'}
        with self.assertRaises(ValueError):
            await existing_application_request(ollama, router, "Return there", context)

    async def test_attachment_request_cannot_replay_stale_field_text(self):
        from olive.interaction.interpreter import SemanticInterpreter
        wrong = {"confidence": 1, "clarification": "", "steps": [{"intent": "browser.interact",
            "entities": {"target": "Body", "text": "Earlier field value"}, "references": {}}]}
        correct = {"confidence": 1, "clarification": "", "steps": [{"intent": "communication.attach",
            "entities": {}, "references": {"path": "path"}}]}
        ollama = SimpleNamespace(chat_measured=AsyncMock(side_effect=[{"content": json.dumps(wrong)},
                                                                     {"content": json.dumps(correct)}]))
        interpreter = SemanticInterpreter(ollama, SimpleNamespace(route=lambda request: SimpleNamespace(name="qwen3:8b", role=request.role)))
        interpreter.speech_act = AsyncMock(return_value={"mode": "action", "domains": ["browser", "communication"]})
        result = await interpreter.interpret("Attach that file.", {"entities": {
            "text": "Earlier field value", "target": "Body", "path": "C:/fixture/report.pdf"}})
        self.assertEqual(result, correct)
        self.assertIn("earlier field content", interpreter.metrics[1]["validation_error"])

    async def test_reprepared_pending_action_retains_reviewed_native_body(self):
        context = InteractionContext(pending={"id": "same-draft", "type": "communication",
            "state": "prepared", "prepared_body": "hello", "entities": {
                "application": "Example", "recipient": "John", "message": "hello everyone"}})
        router = CapabilityRouter(SimpleNamespace(desktop=SimpleNamespace()))
        await router.execute({"intent": "communication.compose", "entities": {}, "references": {}}, context)
        self.assertEqual(context.pending["id"], "same-draft")
        self.assertEqual(context.pending["prepared_body"], "hello")
        self.assertEqual(context.pending["entities"]["message"], "hello everyone")
        self.assertEqual(context.pending["entities"]["recipient"], "John")
        self.assertEqual(context.pending["state"], "prepared")

    def test_navigation_rejects_non_web_targets_before_provider_execution(self):
        from olive.interaction.intent import parse
        for url in ("about:blank", "Chrome", "file:///private.txt", "https://user:secret@example.test", "https://example.test/a b"):
            plan = {"confidence": 1, "clarification": "", "steps": [{"intent": "browser.navigate",
                    "entities": {"url": url}, "references": {}}]}
            with self.assertRaisesRegex(ValueError, "Navigation requires"):
                parse(json.dumps(plan))
        plan["steps"][0]["entities"]["url"] = "https://example.test/"
        self.assertEqual(parse(json.dumps(plan)), plan)

    async def test_disagreeing_control_scope_uses_reasoning_without_granting_authority(self):
        from olive.interaction.control_intent import resolve_control_scope
        ollama = SimpleNamespace(chat_measured=AsyncMock(side_effect=[
            {"content": '{"objects":["task"]}'}, {"content": '{"objects":["media"]}'}]))
        roles = []
        def route(request):
            roles.append(request.role)
            return SimpleNamespace(name="qwen3:8b", role=request.role)
        value = {"clarification": "", "steps": [{"intent": "task.pause", "entities": {}, "references": {}}]}
        result = await resolve_control_scope(ollama, SimpleNamespace(route=route), "Pause playback", {}, value, ["media"])
        self.assertEqual(roles, ["fast", "reasoning"])
        self.assertEqual(result["steps"][0], {"intent": "media.pause", "entities": {}, "references": {}})

    async def test_compound_control_scope_separates_playback_from_task_and_masks_message(self):
        from olive.interaction.control_intent import resolve_control_scope
        ollama = SimpleNamespace(chat_measured=AsyncMock(return_value={"content": '{"objects":["media"]}'}))
        router = SimpleNamespace(route=lambda request: SimpleNamespace(name="qwen3:8b", role="fast"))
        value = {"clarification": "", "steps": [
            {"intent": "communication.compose", "entities": {"message": "hello"}, "references": {}},
            {"intent": "task.pause", "entities": {}, "references": {}}]}
        result = await resolve_control_scope(ollama, router, "Draft hello then pause the music", {}, value, ["media", "task"])
        self.assertEqual([step["intent"] for step in result["steps"]], ["communication.compose", "media.pause"])
        payload = json.loads(ollama.chat_measured.await_args.args[1][-1]["content"])
        self.assertNotIn("hello", payload["actual_request"])
        self.assertEqual(result["steps"][0]["entities"]["message"], "hello")
        value["steps"][1]["intent"] = "task.pause"
        ollama.chat_measured.return_value = {"content": '{"objects":["communication.send"]}'}
        with self.assertRaises(ValueError):
            await resolve_control_scope(ollama, router, "Wait", {}, value, ["media"])

    async def test_unresolved_contextual_speech_act_gets_bounded_reasoning_retry(self):
        from olive.interaction.interpreter import SemanticInterpreter
        plan = {"confidence": 1., "clarification": "", "steps": [{"intent": "communication.attach",
                "entities": {}, "references": {"path": "path"}}]}
        ollama = SimpleNamespace(chat_measured=AsyncMock(return_value={"content": json.dumps(plan)}))
        router = SimpleNamespace(route=lambda request: SimpleNamespace(name="qwen3:8b", role="fast"))
        interpreter = SemanticInterpreter(ollama, router)
        interpreter.speech_act = AsyncMock(side_effect=[{"mode": "clarify", "domains": ["conversation"]},
                                                       {"mode": "action", "domains": ["communication"]}])
        result = await interpreter.interpret("Attach it", {"entities": {"path": "C:/fixture/report.pdf"}})
        self.assertEqual(result["steps"][0]["intent"], "communication.attach")
        self.assertEqual(interpreter.speech_act.await_count, 2)
        self.assertEqual(interpreter.speech_act.await_args.kwargs, {"role": "reasoning"})

    async def test_research_follow_up_uses_conversation_session(self):
        research = SimpleNamespace(
            create=lambda **args: {"id": "first"},
            start=AsyncMock(return_value={"id": "first", "final_report": ""}),
            follow_up=AsyncMock(return_value={"id": "second", "final_report": ""}))
        from olive.models import Chat
        chat = Chat(id="chat")
        router = CapabilityRouter(SimpleNamespace(desktop=None, research=research, chats={chat.id: chat},
            chat=SimpleNamespace(get=lambda identity: chat.to_dict()), save_chats=lambda: None, publish=lambda *a: None))
        context = InteractionContext(chat_id=chat.id)
        step = {"intent": "research.follow_up", "entities": {"query": "More details"}}
        with self.assertRaisesRegex(ValueError, "Which research"):
            await router.execute(step, context)
        research.follow_up.assert_not_awaited()
        await router.execute({**step, "intent": "research.start"}, context)
        self.assertEqual(context.research_session_id, "first")
        self.assertIn("evidence", await router.execute(step, context))
        research.follow_up.assert_awaited_once_with("first", "More details", project_id=None)
        self.assertEqual(context.research_session_id, "second")
        self.assertEqual(Chat.from_dict(chat.to_dict()).research_session_ids, ["first", "second"])

    async def test_named_launch_overrides_stale_application_reference(self):
        from olive.interaction.application_intent import preserve_application
        ollama = SimpleNamespace(chat_measured=AsyncMock(return_value={"content": '{"application":"Cedar Notes"}'}))
        router = SimpleNamespace(route=lambda request: SimpleNamespace(name="qwen3:8b", role="fast"))
        value = {"clarification": "", "steps": [{"intent": "application.launch", "entities": {},
                  "references": {"application": "application"}}]}
        result = await preserve_application(ollama, router, "Bring Cedar Notes up", value)
        self.assertEqual(result["steps"][0]["entities"], {"application": "Cedar Notes"})
        self.assertEqual(result["steps"][0]["references"], {})
        from olive.interaction.reference_intent import resolve_open_reference
        actual = await resolve_open_reference(ollama, router, "Bring Cedar Notes up",
                                              {"entities": {"application": "Other App"}}, result)
        self.assertEqual(actual, result)
        ollama.chat_measured.assert_awaited_once()

    async def test_browser_exact_field_preserves_text_without_second_model_plan(self):
        from olive.interaction.browser import BrowserInteraction
        desktop = SimpleNamespace(browser_observe=AsyncMock(return_value={"controls": [
            {"id": "field", "name": "Message", "enabled": True},
            {"id": "other", "name": "Body", "enabled": True}]}),
            browser_action=AsyncMock(return_value={"verified": True}))
        services = SimpleNamespace(desktop=desktop)
        await BrowserInteraction(services).execute({"entities": {
            "target": "Message", "action": "set_text", "text": "Hello from OLIVE"}}, SimpleNamespace(tab_id="tab"))
        desktop.browser_action.assert_awaited_once_with(target_id="field", action="fill", value="Hello from OLIVE", expected="")
        desktop.browser_action.reset_mock()
        await BrowserInteraction(services).execute({"entities": {
            "target": "Message", "text": "Hello from OLIVE"}}, SimpleNamespace(tab_id="tab"))
        desktop.browser_action.assert_awaited_once_with(target_id="field", action="fill", value="Hello from OLIVE", expected="")

    def test_timestamp_filter_runs_before_result_limit(self):
        from olive.tools.filesystem import FilesystemTool
        with tempfile.TemporaryDirectory() as directory:
            for index in range(40):
                path = Path(directory) / f"old-{index}.pdf"
                path.touch()
                os.utime(path, ns=(100, 100))
            selected = Path(directory) / "selected.pdf"
            selected.touch()
            os.utime(selected, ns=(1000000000, 1000000000))
            result = FilesystemTool("search", ("filesystem.read",))._execute({
                "path": directory, "pattern": "*.pdf", "limit": 30,
                "after_ns": 500000000, "before_ns": 2000000000, "files_only": True})
            self.assertEqual([Path(p) for p in result.data["paths"]], [selected])
            self.assertFalse(result.data["truncated"])

    async def test_selected_document_answer_gets_semantic_reference_pass(self):
        from olive.interaction.interpreter import SemanticInterpreter
        result = {"confidence": 1, "clarification": "", "steps": [{
            "intent": "knowledge.query", "entities": {}, "references": {"path": "path"}}]}
        ollama = SimpleNamespace(chat_measured=AsyncMock(return_value={"content": '{"source":"selected_document"}'}))
        router = SimpleNamespace(route=lambda request: SimpleNamespace(name="qwen3:8b", role="fast"))
        interpreter = SemanticInterpreter(ollama, router)
        interpreter.speech_act = AsyncMock(return_value={"mode": "answer", "domains": ["conversation"]})
        actual = await interpreter.interpret("Summarize it", {"entities": {"path": "selected.pdf"}})
        self.assertEqual(actual, result)
        ollama.chat_measured.assert_awaited_once()

    def test_empty_text_action_is_not_an_executable_interpretation(self):
        from olive.interaction.intent import parse
        with self.assertRaises(ValueError):
            parse(json.dumps({"confidence": 1, "clarification": "", "steps": [
                {"intent": "application.control", "entities": {"target": "A song", "action": "set_text"}, "references": {}}]}))
    def test_navigation_title_verification_is_not_sidebar_or_partial_name(self):
        from olive.desktop.verification import matches
        expected = {"control_type": "Window", "name_token": "general"}
        self.assertTrue(matches({"control_type": "Window", "name": "#general | Example - Client"}, expected))
        for kind, name in (("Hyperlink", "general"), ("Text", "general"),
                           ("Window", "general2"), ("Window", "not-general")):
            self.assertFalse(matches({"control_type": kind, "name": name}, expected))

    def test_cross_app_context_retains_file_and_restores_only_app_navigation(self):
        context = InteractionContext(entities={"application": "Chat App", "server": "Cedar", "channel": "news", "path": "report.pdf"})
        context.accept({"intent": "application.launch", "entities": {"application": "Browser"}})
        self.assertNotIn("channel", context.entities)
        self.assertEqual(context.entities["path"], "report.pdf")
        step = context.resolve({"intent": "application.launch", "entities": {}, "references": {"application": "previous_application"}})
        self.assertEqual(step["entities"]["application"], "Chat App")
        context.accept(step)
        self.assertEqual(context.entities["channel"], "news")
        self.assertEqual(context.entities["previous_application"], "Browser")

    async def test_settings_semantics_use_existing_authorized_navigation(self):
        desktop = SimpleNamespace(open_settings=AsyncMock(return_value={"verified": True}), plan=AsyncMock())
        router = CapabilityRouter(SimpleNamespace(desktop=desktop))
        await router.execute({"intent": "application.navigate", "entities": {"settings_page": "bluetooth"}}, InteractionContext())
        desktop.open_settings.assert_awaited_once_with("bluetooth")
        desktop.plan.assert_not_awaited()

    def file_spec(self, **changes):
        return {"name": "", "name_match": "any", "extension": "pdf", "location": "",
                "time": "yesterday", "absolute_date": "", "timestamp": "downloaded", "recency": "all", **changes}

    def test_relative_dates_and_filename_constraints(self):
        value = constraints(self.file_spec(), "2026-01-01")
        self.assertEqual(value["query"], "*.pdf")
        self.assertEqual((value["date"], value["date_until"]), ("2025-12-31", "2026-01-01"))
        self.assertEqual(value["path"], "Downloads")
        partial = constraints(self.file_spec(name="report", name_match="contains", extension="", time="none"), "2026-09-08")
        self.assertEqual(partial["query"], "*report*")
        self.assertNotIn("date", partial)
        week = constraints(self.file_spec(time="this_week"), "2026-09-08")
        self.assertEqual((week["date"], week["date_until"]), ("2026-09-07", "2026-09-09"))

    def test_unknown_constraints_and_path_injection_rejected(self):
        for spec in (self.file_spec(permission="allow"), self.file_spec(time="arbitrary"),
                     self.file_spec(name="../private", name_match="exact")):
            with self.assertRaises(ValueError):
                constraints(spec, "2026-09-08")

    async def test_file_search_preserves_only_unambiguous_complete_result(self):
        selected = "C:/approved/report.pdf"
        async def tool(name, arguments, *args):
            if name == "filesystem.search":
                return {"paths": [selected, "C:/approved/older.pdf"], "truncated": truncated}
            return {"is_file": True, "modified_ns": int(datetime(2026, 9, 7 if arguments["path"] == selected else 6, 12).timestamp() * 1e9)}
        services = SimpleNamespace(desktop=SimpleNamespace(), agent=SimpleNamespace(tool=tool))
        router = CapabilityRouter(services)
        router.path = lambda value, context: value
        step = {"intent": "filesystem.search", "entities": {"query": "*.pdf", "path": "C:/approved",
                "date": "2026-09-07", "date_until": "2026-09-08", "time_basis": "downloaded"}}
        for truncated in (False, True):
            context = InteractionContext()
            result = await router.execute(step, context)
            self.assertEqual(context.file_candidates, [selected])
            self.assertEqual(context.entities.get("path"), None if truncated else selected)
            self.assertIn("download dates are not available", result)
            if not truncated:
                resolved = context.resolve({"intent": "filesystem.open", "entities": {}, "references": {"path": "path"}})
                self.assertEqual(resolved["entities"]["path"], selected)

    async def test_latest_file_selects_only_unique_newest_complete_result(self):
        for truncated, tied, order in ((False, False, "latest"), (True, False, "latest"),
                                       (False, True, "latest"), (False, False, "all")):
            with self.subTest(truncated=truncated, tied=tied, order=order):
                async def tool(name, arguments, *args):
                    if name == "filesystem.search":
                        return {"paths": ["older.pdf", "newest.pdf"], "truncated": truncated}
                    return {"is_file": True, "modified_ns": 2000000000 if tied or arguments["path"] == "newest.pdf" else 1000000000}
                router = CapabilityRouter(SimpleNamespace(desktop=SimpleNamespace(), agent=SimpleNamespace(tool=tool)))
                router.path = lambda value, context: value
                context = InteractionContext()
                await router.execute({"intent": "filesystem.search", "entities": {
                    "query": "*.pdf", "path": "approved", "order": order}}, context)
                expected = "newest.pdf" if not truncated and not tied and order == "latest" else None
                self.assertEqual(context.entities.get("path"), expected)
                self.assertEqual(set(context.file_candidates), {"older.pdf", "newest.pdf"})

    async def test_pending_update_is_literal_and_never_approval(self):
        model_router = SimpleNamespace(route=lambda request: SimpleNamespace(name="qwen3:8b", role="fast"))
        ollama = SimpleNamespace(chat_measured=AsyncMock(side_effect=[
            {"content": '{"operation":"revise"}'}, {"content": json.dumps({
            "operation": "revise", "updates": [{"field": "message", "value": "hello everyone"}]})}]))
        result = await pending_request(ollama, model_router, "Actually say hello everyone", {"entities": {"recipient": "John"}})
        self.assertEqual(result["steps"][0]["intent"], "task.correct")
        self.assertEqual(result["steps"][0]["entities"], {"message": "hello everyone"})
        ollama.chat_measured.side_effect = [{"content": '{"operation":"revise"}'},
            {"content": '{"operation":"revise","updates":[{"field":"approved","value":"yes"}]}'}]
        with self.assertRaises(ValueError):
            await pending_request(ollama, model_router, "yes", {})

    async def test_revision_framing_is_separate_from_literal_replacement(self):
        from olive.interaction.pending_intent import replacement_wording
        model = SimpleNamespace(name="qwen3:8b", role="fast")
        ollama = SimpleNamespace(chat_measured=AsyncMock(return_value={"content": json.dumps({
            "instruction": "I meant", "replacement": "thanks for your help"})}))
        text = "I meant thanks for your help"
        self.assertEqual(await replacement_wording(ollama, model, text, {}), "thanks for your help")
        for payload in ({"instruction": "I meant", "replacement": text},
                        {"instruction": "I meant", "replacement": "invented wording"},
                        {"instruction": "I meant", "replacement": "thanks", "approved": True}):
            ollama.chat_measured.return_value = {"content": json.dumps(payload)}
            with self.assertRaises(ValueError):
                await replacement_wording(ollama, model, text, {})
