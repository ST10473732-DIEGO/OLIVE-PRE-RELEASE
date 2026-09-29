"""One user-authored front door; context is scoped to conversations, not observations."""

import asyncio
import re
from copy import deepcopy
from .context import InteractionContext
from ..models import chat_title
from .interpreter import SemanticInterpreter
from .router import CapabilityRouter
from ..desktop.errors import ObservationUnavailable
from .request_consent import actual_user_request
from ..authority.owner import owner_request
from .trace import traced_request, event as trace_event
from .workspace_reference import selected_workspace_reference


def bind_search_result(step, executed, context):
    """'Find X in DIR and copy it': 'it' is the search's single verified result.

    Only when the preceding step of THIS request searched exactly the folder the
    proposal names and selected one file inside it. Never a historical file.
    """
    from pathlib import Path
    if step['intent'] not in {'filesystem.copy', 'filesystem.move', 'filesystem.trash', 'filesystem.open'}:
        return step
    if not executed or executed[-1]['intent'] != 'filesystem.search':
        return step
    searched, named, found = executed[-1]['entities'].get('path'), step['entities'].get('path'), context.entities.get('path')
    try:
        folder = Path(searched).expanduser().resolve() if searched else None
        same = folder is not None and named and Path(named).expanduser().resolve() == folder
        inside = found and folder in Path(found).resolve().parents
    except (OSError, RuntimeError, ValueError, TypeError):
        return step
    if not (same and inside and len(context.file_candidates) == 1):
        return step
    bound = deepcopy(step)
    bound['entities']['path'] = found
    trace_event('result_bound', capability=step['intent'], kind='ResolvedFileResult')
    return bound


def fold_coding_steps(steps, text):
    """One coding request is one task: it inspects, edits and validates itself.

    Deterministic: a pathless code.inspect and unconditional code.test steps are
    subsumed by a code.modify step, and repeated code.modify steps become one
    carrying the user's literal request (never a model paraphrase).
    """
    if not any(step['intent'] == 'code.modify' for step in steps):
        return steps
    # "run the tests" is validation (done by the task), not running the program.
    tests_only = bool(re.search(r'\brun (?:the |all |its |my )?(?:unit )?tests?\b', text, re.I)) and not re.search(
        r'\b(?:run|start|launch) (?:it|the (?:app|application|program|project|server|site|api))\b', text, re.I)
    folded, modify = [], None
    for step in steps:
        intent = step['intent']
        if intent == 'code.inspect' and not step['entities'].get('path'):
            continue
        if intent == 'code.run' and tests_only:
            continue
        if intent == 'code.test' and not step.get('when'):
            continue
        if intent == 'code.modify':
            if modify is not None:
                continue
            modify = deepcopy(step)
            modify['entities']['query'] = text[:4000]
            folded.append(modify)
            continue
        folded.append(step)
    if folded != steps:
        trace_event('coding_steps_folded', before=len(steps), after=len(folded))
    return folded


def step_activity(scope):
    """Concise inline progress, never reasoning."""
    app = scope.application or 'the application'
    return {'open': f'Opening {app}…', 'visit': f'Opening the page in {app}…', 'read': f'Reading the page in {app}…',
            'search': f'Searching in {app}…', 'click': f'Finding {scope.content} in {app}…',
            'edit_save': f'Writing and saving in {app}…', 'paste_save': f'Pasting and saving in {app}…',
            'send': f'Sending in {app}…', 'draft': f'Typing the draft in {app}…', 'summarize': 'Summarizing the verified page…',
            'copy': f'Copying in {app}…', 'move': f'Moving in {app}…',
            'go': f'Opening {scope.destination} in {app}…'}.get(scope.effect, 'Working…')


class NaturalLanguageOrchestrator:
    def __init__(self, services, interpreter=None, router=None):
        self.s = services
        self.interpreter = interpreter or SemanticInterpreter(services.ollama, services.model_router)
        self.router = router or CapabilityRouter(services)
        self.contexts = {}
        self.request_traces = []
        self.active = {}
        self.gates = {}
        self.interpreting = {}
        self.selected_workspace = None
        self.selected_file = None
        if hasattr(services, "tool_registry"):
            from .documents import SelectedDocumentTool
            services.tool_registry.register(SelectedDocumentTool(services))
            from .documents import ProjectDocumentTool
            services.tool_registry.register(ProjectDocumentTool(services))
            from .indexed_files import IndexedFileSearchTool
            services.tool_registry.register(IndexedFileSearchTool(services))
        if hasattr(services, "notes"):
            from ..notes.chat import NotesChat
            self.notes_chat = NotesChat(services, self)

    def select_workspace(self, workspace_id):
        if workspace_id is not None and workspace_id not in self.s.workspace_repo.load_all():
            raise ValueError("Unknown workspace")
        self.selected_workspace = workspace_id
        self.selected_file = None

    def context(self, chat_id):
        if chat_id not in self.s.chats:
            raise ValueError("Unknown conversation")
        if chat_id not in self.contexts:
            if len(self.contexts) >= 100:
                idle = next((key for key in self.contexts
                             if key not in self.active and key not in self.interpreting), None)
                if idle is None:
                    raise ValueError("Too many active interactions")
                self.contexts.pop(idle)
            chat = self.s.chats[chat_id]
            research_ids = getattr(chat, "research_session_ids", [])
            self.contexts[chat_id] = InteractionContext(project_id=chat.project_id, chat_id=chat_id,
                research_session_id=research_ids[-1] if research_ids else None)
        return self.contexts[chat_id]

    def presentation_context(self, chat_id=None):
        """Bounded user-facing selection, without planner internals or file contents."""
        from pathlib import Path
        chat_id = chat_id or self.s.current_chat_id
        context = self.context(chat_id)
        workspace_id = self.selected_workspace or context.workspace_id
        workspace = self.s.workspace_repo.load_all().get(workspace_id)
        path = self.selected_file or context.entities.get("path")
        return {"workspace": workspace.title if workspace else "",
                "file": Path(path).name if isinstance(path, str) and path else ""}

    def clear_context(self, chat_id=None):
        """Explicitly clear workspace/file selection; never mutate a pending action."""
        chat_id = chat_id or self.s.current_chat_id
        if chat_id in self.active or self.interpreting.get(chat_id):
            raise ValueError("Stop the current request before clearing its context")
        context = self.context(chat_id)
        self.selected_workspace = self.selected_file = None
        context.workspace_id = None
        context.project_id = self.s.chats[chat_id].project_id
        context.studio_selection = None
        context.editor_context = None
        context.entities.pop("path", None)
        context.file_candidates.clear()
        return self.presentation_context(chat_id)

    @actual_user_request
    @traced_request
    @selected_workspace_reference
    @owner_request
    async def submit(self, text, chat_id=None, research_mode="", workspace_id=""):
        if research_mode not in {"", "Quick", "Deep"}:
            raise ValueError("Unknown research mode")
        chat_id = chat_id or self.s.current_chat_id
        context = self.context(chat_id)
        if getattr(self.s.chats[chat_id], "preset", "") in {"reimagine", "audio", "video"}:
            # Generation modes: Send goes straight to the local media pipeline.
            # No interpreter, research routing or tool planning sees the request.
            return await self.s.chat.send(chat_id, text)
        notes_chat = getattr(self, "notes_chat", None)
        if notes_chat is not None and not research_mode:
            # Literal OLIVE Notes requests are local and run before research or
            # desktop routing: "Open OLIVE Notes" never becomes an app launch,
            # and "search my notes" never becomes a web query.
            handled = await notes_chat.handle(chat_id, text)
            if handled is not None:
                return handled
        if getattr(self.s.chats[chat_id], "preset", "") == "now":
            from .request_consent import requested_capability
            with requested_capability("now.answer"):
                return await self.s.chat.send(chat_id, text)
        if hasattr(self.s, "chat_research"):
            from ..services.chat_research_service import research_intent
            kind = research_intent(self.s.chats[chat_id], text, research_mode)
            if kind:
                from .request_consent import requested_capability
                with requested_capability("now.answer"):
                    return await self.s.chat.send(chat_id, text, research_kind=kind)
        from .task_goal import derive_goal
        goal = derive_goal(text)  # Typed constraints/conditions from literal user bytes only.
        # Only literal local user input reaches native task authority. Remote targets
        # and Studio selection never acquire desktop scope through interpretation.
        native = getattr(getattr(self.s, 'desktop', None), 'linux', None)
        native_allowed = bool(native and not research_mode and
            not getattr(self.s.chat, 'targets', {}).get(chat_id) and
            self.s.desktop.configuration().get('trusted_tasks'))
        if native_allowed:
            # Natural desktop navigation and follow-ups ("Go back", "Open general",
            # "2" after a window question). Deterministic; the bounded context only
            # names the application/window/server OLIVE already verified.
            from ..desktop.navigation_requests import CONTINUE, contextual_request
            navigation_context = await asyncio.to_thread(native.navigation_context, chat_id)
            interrupted = self._interrupted_desktop_task(chat_id)
            if interrupted and not navigation_context.pending_now() and CONTINUE.fullmatch(text.strip().rstrip('.!')):
                return self._decline_desktop_replay(text, chat_id, interrupted)
            try:
                navigation = contextual_request(text, navigation_context)
            except (ValueError, PermissionError) as error:
                return self.reply(chat_id, text, str(error).removeprefix('NEEDS_USER_CLARIFICATION: '))
            if navigation is not None:
                return await self._native_submit(text, chat_id)
            from ..desktop.task_plan import explicit_plan
            plan = explicit_plan(text)
            if plan is not None:
                from ..desktop.task_authority import direct_scope
                try:
                    for clause in plan.clauses:
                        direct_scope(clause)
                except ValueError:
                    pass  # Dependent/freeform clauses use the same typed task loop below.
                else:
                    return await self._native_submit(text, chat_id, plan=plan)
            from ..desktop.task_authority import direct_scope
            try:
                direct_scope(text)
            except ValueError:
                pass  # Freeform interpretation below can still propose a bounded task.
            else:
                return await self._native_submit(text, chat_id)
        selection = (workspace_id or self.selected_workspace, None if workspace_id else self.selected_file)
        if selection[0] and context.studio_selection != selection:
            workspace = self.s.workspace_repo.load_all().get(selection[0])
            if workspace:
                context.workspace_id = workspace.id
                context.project_id = workspace.project_id
                if selection[1]:
                    context.entities["path"] = selection[1]
                context.studio_selection = selection
        correction = self._task_correction(text, chat_id)
        if correction:
            return correction
        interpreting = self.interpreting.setdefault(chat_id, set())
        interpreting.add(asyncio.current_task())
        self.s.publish("interaction_activity", {"chat_id": chat_id, "message": "Understanding your request…"})
        uncensored_choice = None
        interpreter = self.interpreter
        try:
            chat = self.s.chats[chat_id]
            if getattr(chat, 'preset', '') == "uncensored":
                if getattr(self.s.chat, 'targets', {}).get(chat_id):
                    raise ValueError("Remote AI supports OLIVE FAST, NORMAL and MAX. UNCENSORED, DEEP and REIMAGINE are unavailable remotely.")
                self.s.uncensored_router.require_local(self.s.ollama)
                uncensored_choice = self.s.uncensored_router.select(text)
                interpreter = SemanticInterpreter(
                    self.s.uncensored_router.interpreter_provider(self.s.ollama, uncensored_choice),
                    self.s.uncensored_router.for_request(uncensored_choice))
                trace_event('uncensored_route', model=uncensored_choice.model,
                            tier=uncensored_choice.tier, reason=uncensored_choice.reason)
            snapshot = context.snapshot()
            snapshot['native_tasks'] = native_allowed
            snapshot['attached_documents'] = [{'attachment_id':ref.id,'name':ref.name,'kind':ref.kind}
                for ref in self.s.chats[chat_id].documents][:50]
            if hasattr(self.s,'personal'):
                from datetime import datetime
                from ..personal.validation import zone
                profile=self.s.personal.records.profile()
                snapshot['local_date']=datetime.now(zone(profile['timezone'])).date().isoformat()
                snapshot['profile_timezone']=profile['timezone']
            if hasattr(self.s, "project_repo"):
                snapshot["saved_project_names"] = [p.title for p in self.s.project_repo.load_all().values()][:50]
            snapshot["active_task"] = {"state": "running" if self.gates[chat_id].is_set() else "paused"} if chat_id in self.active else None
            if research_mode:
                context.research_depth = research_mode
                interpretation = {"confidence": 1, "clarification": "", "steps": [
                    {"intent": "research.start", "entities": {"query": text}, "references": {}}]}
            else:
                context.research_depth = None
                from ..authority.owner import starter_request
                from .project_request import project_request, resolve_name
                starter = starter_request(text)
                project = None if starter else project_request(text)
                if starter:
                    interpretation = {'confidence':1, 'clarification':'', 'steps':[
                        {'intent':'project.create', 'entities':{'project':starter[0], 'language':starter[1], 'query':text}, 'references':{}}]}
                elif project and not getattr(self.s.chat, 'targets', {}).get(chat_id):
                    # Literal, deterministic: the same spec the owner grant was derived from.
                    interpretation = {'confidence':1, 'clarification':'', 'steps':[
                        {'intent':'project.create', 'entities':{'project':resolve_name(project, str(self.s.data_dir)),
                         'language':project['language'], 'query':text}, 'references':{}}]}
                elif context.coding_follow_up and context.workspace_id:
                    # A follow-up edit to this conversation's own coding task (bounded, literal).
                    interpretation = {'confidence':1, 'clarification':'', 'steps':[
                        {'intent':'code.modify', 'entities':{'query':text}, 'references':{}}]}
                else:
                    from .ordinary_requests import ordinary_request
                    transfer = ordinary_request(text)
                    if transfer is None:
                        from .goal_program import conditional_test_program
                        transfer = conditional_test_program(text, goal)
                    interpretation = transfer or await interpreter.interpret(text, snapshot)
            context.last_interpretation = deepcopy({k:v for k,v in interpretation.items() if k != 'native_plan'})
            if chat_id not in self.active:
                context.resolved_steps = []
        except TimeoutError:
            return self.reply(chat_id, text, "Understanding your request took too long. Please try again.")
        except (ValueError, RuntimeError) as error:
            return self.reply(chat_id, text, str(error))
        except asyncio.CancelledError:
            return self.reply(chat_id, text, "Stopped before starting an action.")
        finally:
            if interpreter is not self.interpreter:
                self.interpreter.metrics.extend(interpreter.metrics)
                self.interpreter.metrics[:] = self.interpreter.metrics[-50:]
            interpreting.discard(asyncio.current_task())
            if not interpreting:
                self.interpreting.pop(chat_id, None)
        if interpretation["clarification"] or interpretation["confidence"] < .75:
            question = interpretation["clarification"] or "Could you clarify what you'd like me to do?"
            context.clarification = {"request": text[:2000], "question": question}
            context.remember_user(text)
            return self.reply(chat_id, text, question)
        steps = interpretation["steps"]
        if native_allowed and interpretation.get('native_plan'):
            return await self._native_submit(text, chat_id, plan=interpretation['native_plan'])
        trace_event('interpreted', intents=[step['intent'] for step in steps],
                    confidence=interpretation['confidence'])
        if getattr(self.s.chat, 'targets', {}).get(chat_id) and (
                len(steps) != 1 or steps[0]['intent'] != 'conversation.answer'):
            return self.reply(chat_id, text,
                'Remote AI provides text answers only. Select This device to use actions, Research or local documents. No remote action was performed.')
        if native_allowed and steps and all(step['intent'] in {
                'application.launch', 'application.activate', 'application.search', 'application.control'} for step in steps):
            return await self._native_submit(text, chat_id, steps)
        if (hasattr(self.s, "chat_research") and len(steps) == 1 and steps[0]["intent"] in {"research.start", "research.follow_up"}
                and not re.search(r"\b(create|export|save|write)\b.*\breport\b", text, re.I)):
            from ..services.chat_research_service import research_intent
            from .request_consent import requested_capability
            kind = research_intent(self.s.chats[chat_id], text, "Quick")
            with requested_capability("now.answer"):
                return await self.s.chat.send(chat_id, text, research_kind=kind)
        if len(steps) == 1 and steps[0]["intent"] in {"conversation.answer", "knowledge.query"}:
            document = {}
            if chat_id in self.active:
                return self.reply(chat_id, text, "Your task is still running. You can pause or cancel it here.")
            if steps[0]["intent"] == "knowledge.query":
                self.active[chat_id] = asyncio.current_task()
                self.gates[chat_id] = asyncio.Event()
                self.gates[chat_id].set()
                try:
                    resolved = context.resolve(steps[0])
                    path = resolved["entities"].get("path")
                    attachment_id = resolved["entities"].get("attachment_id")
                    if attachment_id:
                        if path or attachment_id not in {ref.id for ref in self.s.chats[chat_id].documents}:
                            raise ValueError("Select an attached document from this conversation.")
                        document = {'document_id':attachment_id}
                    elif path:
                        if path != context.entities.get("path") and path not in text:
                            raise ValueError("Please select the document you want me to read.")
                        from pathlib import Path
                        if not Path(path).is_absolute():
                            raise ValueError("Please select the actual document path, or refer to an attached document by its name.")
                        document = await self.s.agent.tool("knowledge.read_selected", {"path": path, "chat_id": chat_id}, "Read the selected document")
                except asyncio.CancelledError:
                    return self.reply(chat_id, text, "Stopped reading the document. No answer was generated.")
                except TimeoutError:
                    return self.reply(chat_id, text, "Reading the document took too long. Please try again.")
                except (ValueError, LookupError, PermissionError) as error:
                    return self.reply(chat_id, text, str(error))
                finally:
                    self.active.pop(chat_id, None)
                    self.gates.pop(chat_id, None)
            context.remember_user(text)
            selection = {"selected_document_id": document["document_id"]} if document.get("document_id") else {}
            if uncensored_choice:
                selection["uncensored_selection"] = uncensored_choice
            return await self.s.chat.send(chat_id, text, **selection)
        control = steps[0]["intent"] if len(steps) == 1 else ""
        if context.entities.get('draft_id') and control in {'task.correct','task.cancel'} and not context.pending and not context.personal_pending:
            steps[0]['intent']='mail.correct' if control=='task.correct' else 'mail.cancel'
            control=steps[0]['intent']
        if context.personal_pending and control in {'task.correct','task.cancel'} and not context.pending:
            steps[0]['intent']='personal.correct' if control=='task.correct' else 'personal.cancel'
            control=steps[0]['intent']
        if control in {'personal.correct','personal.cancel','mail.correct','mail.cancel'} and chat_id in self.active:
            # Withdraw the old immutable approval before accepting a revision.
            previous=self.active[chat_id]
            previous.cancel()
            await asyncio.gather(previous,return_exceptions=True)
        if control in {"task.cancel", "task.pause", "task.resume"}:
            task = self.active.get(chat_id)
            if not task:
                if control == "task.pause" and context.pending and context.pending.get("state") != "sent":
                    if context.pending.get("submission_uncertain"):
                        return self.reply(chat_id, text, "Further sending is stopped. The earlier submission still needs checking in the application.")
                    context.pending["state"] = "prepared"
                    return self.reply(chat_id, text, "I've kept this as an unsent draft. Nothing will be sent.")
                if control == "task.cancel" and context.pending and context.pending.get("state") != "sent":
                    context.pending = None
                    context.clarification = None
                    return self.reply(chat_id, text, "The pending draft has been cancelled.")
                if control == "task.resume":
                    resumable = self._resumable_coding_task(chat_id)
                    if resumable:
                        return await self._resume_coding(text, chat_id, resumable)
                    desktop_task = self._interrupted_desktop_task(chat_id)
                    if desktop_task:
                        return self._decline_desktop_replay(text, chat_id, desktop_task)
                if not self.CONTROL_PHRASE.fullmatch(text.strip()):
                    # With nothing to control, a misread ordinary message ("Reply with
                    # the word: ready") is simply answered. Nothing can be executed here.
                    context.remember_user(text)
                    return await self.s.chat.send(chat_id, text)
                return self.reply(chat_id, text, "There isn't an active task in this conversation.")
            native = getattr(getattr(self.s, 'desktop', None), 'linux', None)
            if native and native.owner is task:
                # Input grants cannot survive a pause or resume automatically.
                # Stop bypasses inference and persistence before returning a reply.
                native.stop()
                task.cancel()
                return self.reply(chat_id, text, "Desktop control stopped. Submit a new bounded request to continue.")
            if control == "task.cancel":
                task.cancel()
                context.pending = None
            elif control == "task.pause":
                if context.pending and context.pending.get("state") == "awaiting_confirmation":
                    task.cancel()
                    context.pending["state"] = "prepared"
                    return self.reply(chat_id, text, "I've withdrawn the send review and kept the message as an unsent draft.")
                self.gates[chat_id].clear()
            else:
                self.gates[chat_id].set()
            return self.reply(chat_id, text, "Cancellation requested." if control == "task.cancel" else
                              "I'll pause before the next action." if control == "task.pause" else "Continuing.")
        if chat_id in self.active:
            return self.reply(chat_id, text, "Please pause or cancel the current action before changing its request.")
        if chat_id in getattr(self.s.chat, "generations", {}):
            return self.reply(chat_id, text, "Please stop the current answer before starting an action.")
        if control == "task.correct":
            try:
                resolved = context.resolve(steps[0])
            except ValueError as error:
                return self.reply(chat_id, text, str(error))
            if not context.pending or context.pending.get("state") == "sent":
                if set(resolved["entities"]) == {"path"}:
                    context.accept(resolved)
                    return self.reply(chat_id, text, "Using the selected file for your next request.")
                return self.reply(chat_id, text, "What would you like to change?")
            if context.pending.get("submission_uncertain"):
                return self.reply(chat_id, text, "Check the earlier submission in the application before preparing replacement wording.")
            context.pending["entities"].update(resolved["entities"])
            context.pending["state"] = "prepared"
            context.accept(resolved)
            if set(resolved["entities"]) == {"message"}:
                return self.reply(chat_id, text, "I've changed the message to:\n\n" + resolved["entities"]["message"] + "\n\nThe destination is unchanged. Nothing has been sent.")
            return self.reply(chat_id, text, "I've updated the pending message. Nothing has been sent.")
        if control == "task.repeat":
            if not context.last_steps:
                return self.reply(chat_id, text, "Which action would you like me to repeat?")
            steps = deepcopy(context.last_steps)
        return await self._execute_steps(text, chat_id, steps, goal=goal)

    def _resumable_coding_task(self, chat_id):
        repo = getattr(self.s, 'agent_task_repo', None)
        if repo is None or not hasattr(self.s, 'coding'):
            return None
        tasks = [t for t in repo.for_chat(chat_id) if t.kind == 'coding']
        latest = tasks[-1] if tasks else None
        return latest if latest and latest.state in {'paused', 'waiting_user'} else None

    def _decline_desktop_replay(self, text, chat_id, desktop_task):
        """Desktop input is never replayed after a restart: the screen may have changed."""
        desktop_task.note('Not resumed automatically; waiting for a new request', 'info')
        desktop_task.transition('cancelled')
        self.s.agent_task_repo.save(desktop_task)
        self.s.publish('agent', {'id': desktop_task.id, 'kind': 'desktop'})
        uncertain = desktop_task.failure_category in {'external outcome uncertain', 'desktop outcome uncertain'}
        return self.reply(chat_id, text, "The desktop task was interrupted, and the screen may have changed since, "
                          "so I won't repeat any clicks or typing automatically." +
                          (" Its last step may or may not have happened; please check the application." if uncertain else "") +
                          " Tell me what to do next (for example \"Open Firefox and go to github.com\").")

    def _interrupted_desktop_task(self, chat_id):
        repo = getattr(self.s, 'agent_task_repo', None)
        if repo is None:
            return None
        tasks = [t for t in repo.for_chat(chat_id) if t.kind == 'desktop']
        latest = tasks[-1] if tasks else None
        return latest if latest and latest.state in {'paused', 'waiting_user'} and \
            (latest.resume_state or {}).get('reason') == 'application restart' else None

    async def _resume_coding(self, text, chat_id, task):
        """'Continue' in Chat: resume this conversation's paused coding task under the same Stop token."""
        self.active[chat_id] = asyncio.current_task()
        self.gates[chat_id] = asyncio.Event()
        self.gates[chat_id].set()
        chat = self.s.chats[chat_id]
        chat.add_message('user', text)
        self.s.save_chats()
        try:
            result = await self.s.coding.runner.resume(task.id)
            answer = result.completion_summary
        except asyncio.CancelledError:
            answer = 'Stopped. Completed changes were kept; nothing further ran.'
        except (ValueError, PermissionError) as error:
            answer = str(error)
        finally:
            self.active.pop(chat_id, None)
            self.gates.pop(chat_id, None)
        return self.reply(chat_id, text, answer, append_user=False)

    CONTROL_PHRASE = re.compile(r"(?:(?:ok|okay|please|now)[,!.]?\s+)*(?:continue|resume|go on|keep going|carry on|proceed|"
                                r"stop|cancel|abort|pause|hold on|wait|halt)(?:\s+(?:it|that|this|the task|now|please|working))*[.!]?",
                                re.I)

    CORRECTION = re.compile(r"^\s*(?:please\s+)?(?:(?:do not|don't|never|avoid)\s+(?:change|changing|edit|editing|modify|modifying|touch|touching|use|using|add|adding|delete|remove)\b"
                            r"|use\s+.{1,80}\s+instead\b|instead\s+of\b|only\s+(?:change|edit|modify)\b|keep\s+(?:the|my)\b)", re.I)

    def _task_correction(self, text, chat_id):
        """A constraint for the running coding task in this chat, applied before its next proposal.

        Deterministic: the literal user text becomes a constraint; nothing is inferred
        by a model and the constraint can only narrow what the task may change.
        """
        coding = getattr(getattr(self.s, 'coding', None), 'runner', None)
        task = coding.current if coding else None
        if (not task or task.terminal or task.chat_id != chat_id or chat_id not in self.active
                or not self.CORRECTION.search(text) or len(text) > 500):
            return None
        coding.add_constraint(text)
        return self.reply(chat_id, text, "Noted. I'll apply this before the next change: \"" + text.strip()[:200] + "\". "
                          "Changes already made are kept; say \"stop\" to end the task instead.")

    async def _native_submit(self, text, chat_id, interpretation=None, plan=None):
        trace_event("desktop_attempt")
        if chat_id in self.active or chat_id in self.s.chat.generations:
            return self.reply(chat_id, text, 'Stop the current request before replacing it.')
        self.active[chat_id] = asyncio.current_task()
        self.gates[chat_id] = asyncio.Event()
        self.gates[chat_id].set()
        chat = self.s.chats[chat_id]
        if not chat.messages:
            chat.title = chat_title(text)
        message = chat.add_message('user', text)
        self.s.save_chats()
        native = self.s.desktop.linux
        native.chat_id = chat_id
        try:
            if plan is None:
                result = await native.run(text, message.id, interpretation=interpretation)
            elif hasattr(plan, 'steps'):
                from ..desktop.task_results import TaskResults
                from ..desktop.freeform_plan import summarize_result
                from .task_goal import COMPLETED, FAILED, recoverable, running_applications
                goal = getattr(plan, 'goal', None)
                protected = running_applications(goal) if goal else {}
                results, epoch = [], None
                bindings = TaskResults(text, native.authority.epoch)
                stopped_early = ''
                try:
                    async with asyncio.timeout(600):
                        for index, step in enumerate(plan.steps):
                            if epoch is not None and (epoch != native.authority.epoch or self.s.desktop.stop_event.is_set()):
                                raise InterruptedError('Task stopped; remaining effects discarded')
                            if goal:
                                goal.check_effect(step.scope.effect, step.scope.application)
                            self.s.publish('interaction_activity', {'chat_id': chat_id, 'message': step_activity(step.scope)})
                            bindings.epoch = native.authority.epoch
                            if step.scope.effect == 'summarize':
                                result = await summarize_result(self.s, text, step, bindings, str(index))
                            else:
                                attempts = 0
                                while True:
                                    result = await native.run(text, message.id, continuation_epoch=epoch,
                                        bound_step=step, results=bindings)
                                    status = self.s.desktop.record.status
                                    # Bounded repair only when no effect was attempted and the
                                    # failure is a transient observation/launch condition.
                                    if (status == 'needs-human' and goal and attempts == 0 and recoverable(result)
                                            and not self.s.desktop.stop_event.is_set()
                                            and asyncio.current_task() is self.active.get(chat_id)
                                            and goal.repair(f'step {index + 1}: {result}')):
                                        attempts += 1
                                        trace_event('step_replanned', index=index)
                                        epoch = native.authority.epoch
                                        continue
                                    break
                                if self.s.desktop.record.status != 'completed':
                                    results.append(result)
                                    stopped_early = result
                                    if goal:
                                        from .error_categories import labelled
                                        goal.mark(step.scope.effect, FAILED, labelled(result), step.scope.application)
                                    break
                                bindings.epoch = native.authority.epoch
                                if step.scope.effect == 'visit':
                                    bindings.location(str(index), step.scope.content, step.scope.application,
                                        self.s.desktop.record.window.get('window_id'), bindings.epoch)
                                if step.scope.effect == 'click' and step.scope.application:
                                    bindings.link(str(index), step.scope.content, step.scope.application,
                                        self.s.desktop.record.window.get('window_id'), bindings.epoch)
                                if step.scope.effect == 'read':
                                    bindings.observation(str(index), result, bindings.epoch, step.source)
                            results.append(result)
                            if goal:
                                goal.mark(step.scope.effect, COMPLETED,
                                          target=step.scope.application + ' ' + step.scope.content)
                            epoch = native.authority.epoch
                            trace_event('subgoal_verified', index=index, remaining=len(plan.steps)-index-1)
                    result = '\n\n'.join(f'{i+1}. {value}' for i, value in enumerate(results))
                    if goal and (len(goal.requested_effects) >= 2 or goal.constraints):
                        still = running_applications(goal)
                        for app, before in protected.items():
                            if before and not still.get(app):
                                goal.unresolved_requirements.append(app + ' is no longer running')
                        report = goal.finish(failed_detail=stopped_early)
                        kept = [app for app, before in protected.items() if before and still.get(app)]
                        if kept:
                            report += '\n- Verified still running: ' + ', '.join(kept)
                        if goal.unresolved_requirements:
                            report += '\n- Constraint check failed: ' + '; '.join(goal.unresolved_requirements)
                        if goal.replans:
                            report += '\n- Recovered steps: ' + '; '.join(goal.replans)
                        result += '\n\n' + report
                finally:
                    bindings.close()
            else:
                # Resolve all scopes before the first effect, not halfway through.
                from ..desktop.task_authority import direct_scope, interpreted_scope
                proposals = []
                for clause in plan.clauses:
                    try:
                        direct_scope(clause)
                        proposals.append(None)
                    except ValueError:
                        proposal = await self.interpreter.interpret(clause, {})
                        if proposal['clarification'] or proposal['confidence'] < .75:
                            raise ValueError('The combined request needs clarification before any effect')
                        interpreted_scope(clause, proposal['steps'])
                        proposals.append(proposal['steps'])
                results, epoch = [], None
                async with asyncio.timeout(600):
                    for index, (clause, proposal) in enumerate(zip(plan.clauses, proposals)):
                        result = await native.run(clause, message.id, interpretation=proposal, continuation_epoch=epoch)
                        results.append(result)
                        if self.s.desktop.record.status != 'completed':
                            break
                        epoch = native.authority.epoch
                        trace_event('subgoal_verified', index=index)
                if plan.summarize and self.s.desktop.record.status == 'completed':
                    self.s.publish('interaction_activity', {'chat_id':chat_id, 'message':'Summarising the verified visible page…'})
                    # Evidence goes only to answer generation, never interpretation
                    # or a tool planner. The original request remains the user turn.
                    return await self.s.chat.send(chat_id, text, observed_text=results[-1],
                                                  existing_user_message_id=message.id)
                result = '\n\n'.join(f'{i+1}. {value}' for i,value in enumerate(results))
            return self.reply(chat_id, text, result, append_user=False)
        except (ValueError, PermissionError, InterruptedError, TimeoutError, RuntimeError) as error:
            from .error_categories import labelled
            completed = locals().get('results', [])
            prefix = '\n\n'.join(f'{i+1}. {value}' for i, value in enumerate(completed))
            goal = getattr(plan, 'goal', None) if plan is not None else None
            report = ('\n\n' + goal.finish(cancelled=isinstance(error, InterruptedError), failed_detail=labelled(error))
                      if goal and (len(goal.requested_effects) >= 2 or goal.constraints) else '')
            return self.reply(chat_id, text, (prefix + '\n\n' if prefix else '') +
                              'Task incomplete: ' + labelled(error) + report, append_user=False)
        except asyncio.CancelledError:
            prefix = '\n\n'.join(f'{i+1}. {value}' for i,value in enumerate(locals().get('results', [])))
            goal = getattr(plan, 'goal', None) if plan is not None else None
            report = ('\n\n' + goal.finish(cancelled=True)
                      if goal and (len(goal.requested_effects) >= 2 or goal.constraints) else '')
            return self.reply(chat_id, text, (prefix + '\n\n' if prefix else '') +
                'Stopped. Inspect any uncertain effect before requesting it again.' + report, append_user=False)
        finally:
            native.chat_id = None
            self.active.pop(chat_id, None)
            self.gates.pop(chat_id, None)

    @actual_user_request
    async def research_question(self, question, chat_id, depth='Standard', project_id=None):
        """The explicit Research form selects a capability, never a permission.

        Natural-language follow-ups still enter submit/interpret. The literal
        question is routed through the same context, task lifecycle and router.
        """
        if not isinstance(question, str) or not 1 <= len(question.strip()) <= 4000:
            raise ValueError('Enter a research question of at most 4000 characters')
        if depth not in {'Quick', 'Standard', 'Deep'}:
            raise ValueError('Unknown research depth')
        if project_id and project_id not in self.s.project_repo.load_all():
            raise ValueError('Unknown project')
        if chat_id in self.active or self.interpreting.get(chat_id) or chat_id in self.s.chat.generations:
            raise ValueError('Stop the current request before starting Research')
        context = self.context(chat_id)
        context.project_id = project_id or None
        context.research_depth = depth
        steps = [{'intent': 'research.start', 'entities': {'query': question}, 'references': {}}]
        context.last_interpretation = {'source': 'Explicit user Research form', 'steps': deepcopy(steps)}
        return await self._execute_steps(question, chat_id, steps)

    async def _execute_steps(self, text, chat_id, steps, goal=None):
        from .goal_program import gate as branch_gate, skip, step_effect, MUTATION_GOALS, INTERNAL_SURFACES
        from .task_goal import COMPLETED, FAILED
        context = self.context(chat_id)
        steps = fold_coding_steps(steps, text)
        compound = bool(goal and (len(goal.requested_effects) >= 2 or goal.constraints or goal.conditions))
        if goal and len(goal.requested_effects) >= 2:
            # A multi-effect request must not silently lose a requested change.
            # A coding task step runs the workspace's detected build/tests itself, so it
            # covers a requested test effect; its real result is recorded below.
            planned = [(step_effect(s), '') for s in steps] + [('test', '') for s in steps if s['intent'] == 'code.modify']
            missing = [m for m in goal.completeness(planned) if m.effect in MUTATION_GOALS]
            if missing:
                return self.reply(chat_id, text, 'PLAN_INCOMPLETE: I could not map every requested change to a '
                                  'supported step (' + ', '.join(m.effect.replace('_', ' ') for m in missing) +
                                  '). Nothing was changed. Please split or rephrase the request.')
        self.active[chat_id] = asyncio.current_task()
        gate = self.gates[chat_id] = asyncio.Event()
        gate.set()
        context.remember_user(text)
        chat = self.s.chats[chat_id]
        context.message_id = chat.add_message("user", text).id
        self.s.save_chats()
        messages = []
        executed_steps = []
        context.resolved_steps = executed_steps
        context.last_outcome = None
        cancelled = False
        failure = ''
        try:
            for step in steps:
                await gate.wait()
                reason = branch_gate(step, context.last_outcome, goal) if goal else ''
                if reason:
                    skip(goal, step, reason)
                    trace_event('branch_skipped', capability=step['intent'])
                    continue
                if goal:
                    goal.check_effect(step_effect(step))  # Constraints re-evaluated before each effect.
                step = bind_search_result(step, executed_steps, context)
                resolved = context.resolve(step)
                executed_steps.append(deepcopy(resolved))
                self.s.publish("interaction_activity", {"chat_id": chat_id, "message": "Working on your request…"})
                trace_event("capability_attempt", capability=resolved["intent"])
                messages.append(await self.router.execute(resolved, context))
                context.accept(resolved)
                if goal:
                    goal.mark(step_effect(step), COMPLETED)
                    outcome = context.last_outcome or {}
                    if resolved['intent'] == 'code.modify' and outcome.get('intent') == 'code.modify' and outcome.get('validated'):
                        goal.mark('test', COMPLETED if outcome.get('passed') else FAILED,
                                  '' if outcome.get('passed') else 'checks failed after the change')
                        # "Find the problem" is the task's own diagnosis from the observed checks.
                        goal.mark('search', COMPLETED)
            context.last_steps = deepcopy(executed_steps)
            context.clarification = None
        except asyncio.CancelledError:
            cancelled = True
            messages.append("Stopped. Completed actions have not been undone.")
        except TimeoutError:
            failure = 'timeout'
            messages.append("The action could not be verified before the timeout. I've stopped; please check the application before retrying.")
        except ObservationUnavailable:
            failure = 'observation changed'
            messages.append("The application's controls changed while I was reading them. I've stopped; let the page settle before continuing.")
        except (ValueError, LookupError, PermissionError) as error:
            failure = str(error)
            messages.append(str(error))
            if isinstance(error, (ValueError, LookupError)):
                context.clarification = {"request": text[:2000], "question": str(error)[:500]}
        finally:
            self.active.pop(chat_id, None)
            self.gates.pop(chat_id, None)
        if compound:
            if any(step_effect(s) in {'test', 'run', 'code_edit', 'commit', 'stage', 'create_project'} for s in executed_steps):
                for required in goal.requested_effects:
                    if required.effect == 'open' and required.target in INTERNAL_SURFACES and required.status == 'PENDING':
                        required.status = COMPLETED
            if failure:
                pending = next((r for r in goal.requested_effects if r.status == 'PENDING'), None)
                if pending:
                    pending.status, pending.detail = FAILED, failure[:300]
            messages.append(goal.finish(cancelled=cancelled, failed_detail=failure))
        return self.reply(chat_id, text, "\n\n".join(m for m in messages if m), append_user=False)

    def cancel(self, chat_id):
        if getattr(self.s, 'owner_policy', None):
            self.s.owner_policy.cancel(chat_id)
        native = getattr(getattr(self.s, 'desktop', None), 'linux', None)
        if native and native.owner is not None and native.owner is self.active.get(chat_id):
            native.stop()  # Signal and epoch first; never wait on inference/SQLite.
        for interpreting in list(self.interpreting.get(chat_id, ())):
            interpreting.cancel()
        task = self.active.get(chat_id)
        if task:
            task.cancel()
        self.s.chat.stop(chat_id)

    @actual_user_request
    async def review_native(self,chat_id,proposal_id,revision,decision):
        if decision not in {'commit','cancel'}:raise ValueError('Unknown native review decision')
        if chat_id in self.active or self.interpreting.get(chat_id):raise ValueError('Stop the current request before reviewing a proposal')
        context=self.context(chat_id);proposal=context.personal_pending.get(proposal_id)
        if not proposal or proposal['revision']!=revision:raise ValueError('The proposal changed. Review the current revision.')
        return await self._execute_steps('Review native proposal',chat_id,[{'intent':'personal.'+decision,'entities':{'proposal_id':proposal_id},'references':{}}])

    def inspect(self, chat_id):
        """Explicit developer view, never fed back into user intent or permissions."""
        context = self.context(chat_id)
        return deepcopy({"interpretation": context.last_interpretation, "resolved_steps": context.resolved_steps,
                         "request_traces": [r for r in self.request_traces if r['chat_id']==chat_id][-5:],
                         "interpretation_metrics": getattr(self.interpreter,'metrics',[])[-8:],
                         "browser": context.browser_application, "media": context.media_application,
                         "research_session_id": context.research_session_id,
                         "pending_state": (context.pending or {}).get("state")})

    def edit_draft(self, chat_id, message=None, cancel=False):
        context = self.context(chat_id)
        if chat_id in self.active or self.interpreting.get(chat_id):
            raise ValueError("Stop the current action before editing its draft.")
        if not context.pending or context.pending.get("state") == "sent":
            raise ValueError("There is no unsent draft to edit.")
        if cancel:
            uncertain = context.pending.get("submission_uncertain")
            context.pending = None
            context.clarification = None
            answer = ("I cancelled the pending action. Check the application for the earlier unverified submission."
                      if uncertain else "I cancelled the draft. Nothing was sent.")
        else:
            if context.pending.get("submission_uncertain"):
                raise ValueError("Check the earlier submission in the application before preparing replacement wording.")
            if not isinstance(message, str) or not 1 <= len(message.strip()) <= 4000:
                raise ValueError("Enter a message of up to 4000 characters.")
            context.pending["entities"]["message"] = message
            context.pending["state"] = "prepared"
            answer = "I updated the unsent message. Its destination is unchanged."
        return self.reply(chat_id, "", answer, append_user=False)

    def reply(self, chat_id, text, answer, append_user=True):
        chat = self.s.chats[chat_id]
        if append_user:
            chat.add_message("user", text)
        chat.add_message("assistant", answer)
        self.s.save_chats()
        result = self.s.chat.get(chat_id)
        self.s.publish("chat", result)
        self.s.publish("interaction_activity", {"chat_id": chat_id, "message": "Ready"})
        return result

    async def shutdown(self):
        tasks = list(set(self.active.values()) | {task for group in self.interpreting.values() for task in group})
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
