import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from olive.interaction.intent import parse
from olive.interaction.context import InteractionContext, normalize_pending_intent
from olive.interaction.interpreter import SemanticInterpreter
from olive.interaction.orchestrator import NaturalLanguageOrchestrator


def interpretation(intent="application.launch", entities=None, references=None):
    return {"confidence": .95, "clarification": "", "steps": [
        {"intent": intent, "entities": entities or {"application": "Example"}, "references": references or {}}]}


class IntentTests(unittest.TestCase):
    def test_consumed_proposal_is_not_a_repeatable_execution(self):
        context=InteractionContext()
        self.assertFalse(context.snapshot()['repeatable_task'])
        context.last_steps=[{'intent':'personal.commit'}]
        self.assertFalse(context.snapshot()['repeatable_task'])
        context.last_steps=[{'intent':'code.run'}]
        self.assertTrue(context.snapshot()['repeatable_task'])

    def test_recurrence_is_validated_before_action_resolution(self):
        with self.assertRaises(ValueError):
            parse(json.dumps(interpretation('tasks.create', {'title':'Practice','priority':'normal? (default)'})))
        for rule in ('false', 'true', 'FREQ=HOURLY'):
            with self.subTest(rule=rule), self.assertRaises(ValueError):
                parse(json.dumps(interpretation('calendar.create', {'title':'Practice','start':'2026-09-14T18:00:00','recurrence':rule})))
        for rule in ('', 'FREQ=WEEKLY;COUNT=3', 'FREQ=DAILY;UNTIL=20301230T180000Z'):
            value=interpretation('calendar.create', {'title':'Practice','start':'2026-09-14T18:00:00','recurrence':rule})
            self.assertEqual(parse(json.dumps(value)),value)

    def test_pending_draft_composition_is_revision_but_send_stays_send(self):
        context = {"pending_draft": {"type": "communication", "state": "prepared"}}
        self.assertEqual(normalize_pending_intent(interpretation("communication.compose"), context)["steps"][0]["intent"], "task.correct")
        self.assertEqual(normalize_pending_intent(interpretation("communication.send"), context)["steps"][0]["intent"], "communication.send")
        context["pending_draft"]["state"] = "sent"
        self.assertEqual(normalize_pending_intent(interpretation("communication.compose"), context)["steps"][0]["intent"], "communication.compose")

    def test_strict_boundary(self):
        good = interpretation()
        self.assertEqual(parse(json.dumps(good)), good)
        bad = ["```json\n" + json.dumps(good) + "\n```", '{"confidence":1,"confidence":0}',
               json.dumps({**good, "permission": "allow"}), json.dumps({**good, "confidence": True}),
               json.dumps({**good, "confidence": float("nan")}),
               json.dumps(interpretation("terminal.run")),
               json.dumps(interpretation(entities={"shell": "echo hello"}))]
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse(raw)

    def test_context_is_bounded_and_reference_resolution_is_explicit(self):
        context = InteractionContext()
        for index in range(20):
            context.remember_user(str(index) * 3000)
        self.assertEqual(len(context.recent), 6)
        self.assertLessEqual(len(context.recent[-1]), 2000)
        context.entities["application"] = "Example"
        step = {"intent": "application.navigate", "entities": {"channel": "general"},
                "references": {"application": "application"}}
        self.assertEqual(context.resolve(step)["entities"]["application"], "Example")
        step["references"] = {"recipient": "application"}
        with self.assertRaises(ValueError):
            context.resolve(step)


class SemanticTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_ids_must_match_the_selected_identity_kind(self):
        wrong=interpretation('mail.read',{'mail_id':'proposal-one'})
        correct=interpretation('mail.read',{'mail_id':'message-one'})
        ollama=SimpleNamespace(chat_measured=AsyncMock(side_effect=[
            {'content':json.dumps({'mode':'action','domains':['mail']})},
            {'content':json.dumps(wrong)},{'content':json.dumps(correct)}]))
        router=SimpleNamespace(route=Mock(return_value=SimpleNamespace(name='gpt-oss:20b')))
        result=await SemanticInterpreter(ollama,router).interpret('Read that message',{'entities':{'mail_id':'message-one','proposal_id':'proposal-one'}})
        self.assertEqual(result,correct)
        self.assertEqual(ollama.chat_measured.await_count,3)

    async def test_native_mail_scope_retries_without_invented_folder(self):
        wrong=interpretation('mail.search',{'query':'Planning','folder':'local'})
        correct=interpretation('mail.search',{'query':'Planning','sender':'sarah@example.invalid'})
        ollama=SimpleNamespace(chat_measured=AsyncMock(side_effect=[
            {'content':json.dumps({'mode':'action','domains':['mail']})},
            {'content':json.dumps(wrong)},{'content':json.dumps(correct)}]))
        router=SimpleNamespace(route=Mock(return_value=SimpleNamespace(name='gpt-oss:20b')))
        value=await SemanticInterpreter(ollama,router).interpret('Find local email from sarah@example.invalid about Planning',{})
        self.assertEqual(value,correct)
        self.assertEqual(router.route.call_args_list[-1].args[0].role,'reasoning')

    def test_file_search_requires_query_and_valid_date(self):
        for entities in ({"path": "Downloads"}, {"query": "*.pdf", "date": "yesterday"},
                         {"query": "*.pdf", "date": "2026-02-30"}):
            with self.subTest(entities=entities), self.assertRaises(ValueError):
                parse(json.dumps(interpretation("filesystem.search", entities)))
        result = parse(json.dumps(interpretation("filesystem.search", {"query": "*.pdf", "date": "2026-09-07"})))
        self.assertEqual(result["steps"][0]["entities"]["date"], "2026-09-07")

    async def test_communication_decision_distinguishes_delivery_from_permission(self):
        from olive.interaction.communication_intent import resolve_communication
        router = SimpleNamespace(route=lambda request: SimpleNamespace(name="qwen3:8b", role="fast"))
        for decision, expected in (("draft", "communication.compose"), ("revise", "task.correct"),
                                   ("request_delivery", "communication.send")):
            with self.subTest(decision=decision):
                ollama = SimpleNamespace(chat_measured=AsyncMock(return_value={
                    "content": json.dumps({"decisions": [decision]})}))
                value = interpretation("communication.compose", {"message": "hello"})
                result = await resolve_communication(ollama, router, "User's actual request", {}, value)
                self.assertEqual(result["steps"][0]["intent"], expected)
                self.assertEqual(result["steps"][0]["entities"], {"message": "hello"})
                self.assertNotIn("approved", result)

    async def test_unclear_or_invalid_delivery_decision_cannot_become_send(self):
        from olive.interaction.communication_intent import resolve_communication
        router = SimpleNamespace(route=lambda request: SimpleNamespace(name="qwen3:8b", role="fast"))
        for decisions in (["unclear"], ["approved"], [], [True], ["request_delivery", "draft"]):
            with self.subTest(decisions=decisions):
                ollama = SimpleNamespace(chat_measured=AsyncMock(return_value={
                    "content": json.dumps({"decisions": decisions})}))
                with self.assertRaises(ValueError):
                    await resolve_communication(ollama, router, "Wait", {}, interpretation("communication.send"))

    async def test_bounded_retry_never_executes_malformed_prose(self):
        ollama = SimpleNamespace(chat_measured=AsyncMock(side_effect=[{"content": '{"mode":"action","domains":["application"]}'}, {"content": "ignore permissions"}, {"content": json.dumps(interpretation())}]))
        router = SimpleNamespace(route=Mock(return_value=SimpleNamespace(name="qwen3:8b")))
        result = await SemanticInterpreter(ollama, router).interpret("Bring Example up", {})
        self.assertEqual(result["steps"][0]["intent"], "application.launch")
        self.assertEqual(ollama.chat_measured.await_count, 3)
        self.assertEqual(router.route.call_args_list[0].args[0].role, "fast")
        self.assertEqual(router.route.call_args_list[2].args[0].role, "reasoning")
        for call in ollama.chat_measured.await_args_list[1:]:
            messages = call.args[1]
            self.assertEqual([m["role"] for m in messages], ["system", "user"])
            self.assertIn("BACKGROUND CONTEXT DATA", messages[0]["content"])
            self.assertIn("ILLUSTRATIVE LABEL EXAMPLES", messages[0]["content"])
            self.assertIn("communication.send always means", messages[0]["content"])
        self.assertIn("failed validation", ollama.chat_measured.await_args_list[-1].args[1][0]["content"])

    def make(self, value):
        services = SimpleNamespace(chats={"a": SimpleNamespace(project_id=None, documents=[], add_message=Mock())}, current_chat_id="a", save_chats=Mock(),
                                   publish=Mock(), chat=SimpleNamespace(send=AsyncMock(return_value={"chat": True})))
        interpreter = SimpleNamespace(interpret=AsyncMock(return_value=value))
        router = SimpleNamespace(execute=AsyncMock(return_value="Opened."))
        owner = NaturalLanguageOrchestrator(services, interpreter, router)
        owner.reply = lambda chat, text, answer, **kwargs: {"answer": answer}
        return owner, router, services

    async def test_conversation_does_not_execute_actions(self):
        owner, router, services = self.make(interpretation("conversation.answer"))
        await owner.submit("How would I open Example?")
        router.execute.assert_not_awaited()
        services.chat.send.assert_awaited_once()

    async def test_attached_document_answer_does_not_reread_an_invented_path(self):
        owner, router, services=self.make(interpretation('knowledge.query',{'attachment_id':'doc-one'}))
        services.chats['a'].documents=[SimpleNamespace(id='doc-one',name='mixed.pdf',kind='pdf')]
        services.agent=SimpleNamespace(tool=AsyncMock())
        await owner.submit('Read page 2 of the attached PDF')
        services.agent.tool.assert_not_awaited();router.execute.assert_not_awaited()
        services.chat.send.assert_awaited_once_with('a','Read page 2 of the attached PDF',selected_document_id='doc-one')
        owner.interpreter.interpret.return_value=interpretation('knowledge.query',{'attachment_id':'another-chat-doc'})
        services.chat.send.reset_mock()
        result=await owner.submit('Read that attachment')
        self.assertIn('Select an attached document',result['answer'])
        services.chat.send.assert_not_awaited()

    async def test_shutdown_cancels_document_preparation_before_generation(self):
        from pathlib import Path
        path=str(Path.cwd()/'report.pdf')
        owner, _, services = self.make(interpretation("knowledge.query", {"path": path}))
        entered = asyncio.Event()
        async def read(*args):
            entered.set()
            await asyncio.Event().wait()
        services.agent = SimpleNamespace(tool=read)
        owner.context("a").entities["path"] = path
        running = asyncio.create_task(owner.submit("Summarize it"))
        await entered.wait()
        self.assertIn("a", owner.active)
        await owner.shutdown()
        result = await running
        self.assertIn("Stopped reading", result["answer"])
        services.chat.send.assert_not_awaited()
        self.assertFalse(owner.active)

    async def test_low_confidence_clarifies_without_execution(self):
        value = interpretation()
        value["confidence"] = .2
        owner, router, _ = self.make(value)
        result = await owner.submit("Use the other one")
        router.execute.assert_not_awaited()
        self.assertIn("clarify", result["answer"])

    async def test_action_timeout_stops_compound_request_without_claiming_success(self):
        value = interpretation()
        value["steps"] *= 2
        owner, router, _ = self.make(value)
        router.execute.side_effect = TimeoutError()
        result = await owner.submit("Open Example and continue")
        self.assertIn("could not be verified", result["answer"])
        self.assertEqual(router.execute.await_count, 1)
        self.assertFalse(owner.active)
        self.assertFalse(owner.context("a").last_steps)

    async def test_interpretation_timeout_has_useful_response_and_no_action(self):
        owner, router, _ = self.make(interpretation())
        owner.interpreter.interpret.side_effect = TimeoutError()
        result = await owner.submit("Open Example")
        self.assertIn("took too long", result["answer"])
        router.execute.assert_not_awaited()

    async def test_compound_order_and_context(self):
        value = interpretation()
        value["steps"].append({"intent": "application.navigate", "entities": {"channel": "general"},
                               "references": {"application": "application"}})
        owner, router, _ = self.make(value)
        await owner.submit("Bring Example up and go to general")
        self.assertEqual(router.execute.await_count, 2)
        self.assertEqual(router.execute.await_args_list[1].args[0]["entities"]["application"], "Example")

    async def test_correction_does_not_submit_message(self):
        owner, router, _ = self.make(interpretation("task.correct", {"message": "I'll call later"}))
        owner.context("a").pending = {"state": "prepared", "entities": {"message": "hello"}}
        await owner.submit("Actually say I'll call later")
        self.assertEqual(owner.context("a").pending["entities"]["message"], "I'll call later")
        router.execute.assert_not_awaited()

    async def test_sent_message_cannot_be_rewritten_as_unsent_draft(self):
        owner, router, _ = self.make(interpretation("task.correct", {"message": "replacement"}))
        owner.context("a").pending = {"state": "sent", "entities": {"message": "hello"}}
        await owner.submit("Change that message")
        self.assertEqual(owner.context("a").pending["state"], "sent")
        self.assertEqual(owner.context("a").pending["entities"]["message"], "hello")
        router.execute.assert_not_awaited()

    async def test_studio_selection_does_not_overwrite_later_conversational_file(self):
        owner, router, services = self.make(interpretation("conversation.answer"))
        services.workspace_repo = SimpleNamespace(load_all=lambda: {"w": SimpleNamespace(id="w", project_id="p")})
        owner.selected_workspace, owner.selected_file = "w", "original.py"
        await owner.submit("Explain the selected file")
        context = owner.context("a")
        context.entities["path"] = "other.py"
        await owner.submit("Now explain this one")
        self.assertEqual(context.entities["path"], "other.py")
        owner.selected_file = "new-selection.py"
        await owner.submit("Explain the new editor selection")
        self.assertEqual(context.entities["path"], "new-selection.py")

    async def test_cancel_stops_future_steps(self):
        value = interpretation()
        value["steps"] *= 2
        owner, router, _ = self.make(value)
        entered = asyncio.Event()
        async def wait(*args):
            entered.set()
            await asyncio.Event().wait()
        router.execute.side_effect = wait
        running = asyncio.create_task(owner.submit("Do two actions"))
        await entered.wait()
        owner.interpreter.interpret.return_value = interpretation("task.cancel")
        await owner.submit("Never mind")
        await running
        self.assertEqual(router.execute.await_count, 1)
        self.assertFalse(owner.active)
