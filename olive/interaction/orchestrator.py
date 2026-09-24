"""One user-authored front door; context is scoped to conversations, not observations."""

import asyncio
from copy import deepcopy
from .context import InteractionContext
from .interpreter import SemanticInterpreter
from .router import CapabilityRouter
from ..desktop.errors import ObservationUnavailable
from .request_consent import actual_user_request
from ..authority.owner import owner_request
from .trace import traced_request, event as trace_event
from .workspace_reference import selected_workspace_reference


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
        # Only literal local user input reaches native task authority. Remote targets
        # and Studio selection never acquire desktop scope through interpretation.
        native = getattr(getattr(self.s, 'desktop', None), 'linux', None)
        native_allowed = bool(native and not research_mode and
            not getattr(self.s.chat, 'targets', {}).get(chat_id) and
            self.s.desktop.configuration().get('trusted_tasks'))
        if native_allowed:
            from ..desktop.task_plan import explicit_plan
            plan = explicit_plan(text)
            if plan is not None:
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
        interpreting = self.interpreting.setdefault(chat_id, set())
        interpreting.add(asyncio.current_task())
        self.s.publish("interaction_activity", {"chat_id": chat_id, "message": "Understanding your request…"})
        try:
            snapshot = context.snapshot()
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
                starter = starter_request(text)
                if starter:
                    interpretation = {'confidence':1, 'clarification':'', 'steps':[
                        {'intent':'project.create', 'entities':{'project':starter[0], 'language':starter[1], 'query':text}, 'references':{}}]}
                else:
                    from .ordinary_requests import file_transfer
                    transfer = file_transfer(text)
                    interpretation = transfer or await self.interpreter.interpret(text, snapshot)
            context.last_interpretation = deepcopy(interpretation)
            if chat_id not in self.active:
                context.resolved_steps = []
        except TimeoutError:
            return self.reply(chat_id, text, "Understanding your request took too long. Please try again.")
        except (ValueError, RuntimeError) as error:
            return self.reply(chat_id, text, str(error))
        except asyncio.CancelledError:
            return self.reply(chat_id, text, "Stopped before starting an action.")
        finally:
            interpreting.discard(asyncio.current_task())
            if not interpreting:
                self.interpreting.pop(chat_id, None)
        if interpretation["clarification"] or interpretation["confidence"] < .75:
            question = interpretation["clarification"] or "Could you clarify what you'd like me to do?"
            context.clarification = {"request": text[:2000], "question": question}
            context.remember_user(text)
            return self.reply(chat_id, text, question)
        steps = interpretation["steps"]
        trace_event('interpreted', intents=[step['intent'] for step in steps],
                    confidence=interpretation['confidence'])
        if getattr(self.s.chat, 'targets', {}).get(chat_id) and (
                len(steps) != 1 or steps[0]['intent'] != 'conversation.answer'):
            return self.reply(chat_id, text,
                'Remote AI provides text answers only. Select This device to use actions, Research or local documents. No remote action was performed.')
        if native_allowed and steps and all(step['intent'] in {
                'application.launch', 'application.activate', 'application.search', 'application.control'} for step in steps):
            return await self._native_submit(text, chat_id, steps)
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
        return await self._execute_steps(text, chat_id, steps)

    async def _native_submit(self, text, chat_id, interpretation=None, plan=None):
        trace_event("desktop_attempt")
        if chat_id in self.active or chat_id in self.s.chat.generations:
            return self.reply(chat_id, text, 'Stop the current request before replacing it.')
        self.active[chat_id] = asyncio.current_task()
        self.gates[chat_id] = asyncio.Event()
        self.gates[chat_id].set()
        chat = self.s.chats[chat_id]
        if not chat.messages:
            chat.title = text[:48]
        message = chat.add_message('user', text)
        self.s.save_chats()
        native = self.s.desktop.linux
        native.chat_id = chat_id
        try:
            if plan is None:
                result = await native.run(text, message.id, interpretation=interpretation)
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
        except (ValueError, PermissionError, InterruptedError) as error:
            return self.reply(chat_id, text, str(error), append_user=False)
        except asyncio.CancelledError:
            return self.reply(chat_id, text, 'Stopped. Inspect any uncertain effect before requesting it again.', append_user=False)
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

    async def _execute_steps(self, text, chat_id, steps):
        context = self.context(chat_id)
        self.active[chat_id] = asyncio.current_task()
        gate = self.gates[chat_id] = asyncio.Event()
        gate.set()
        context.remember_user(text)
        chat = self.s.chats[chat_id]
        chat.add_message("user", text)
        self.s.save_chats()
        messages = []
        executed_steps = []
        context.resolved_steps = executed_steps
        try:
            for step in steps:
                await gate.wait()
                resolved = context.resolve(step)
                executed_steps.append(deepcopy(resolved))
                self.s.publish("interaction_activity", {"chat_id": chat_id, "message": "Working on your request…"})
                trace_event("capability_attempt", capability=resolved["intent"])
                messages.append(await self.router.execute(resolved, context))
                context.accept(resolved)
            context.last_steps = deepcopy(executed_steps)
            context.clarification = None
        except asyncio.CancelledError:
            messages.append("Stopped. Completed actions have not been undone.")
        except TimeoutError:
            messages.append("The action could not be verified before the timeout. I've stopped; please check the application before retrying.")
        except ObservationUnavailable:
            messages.append("The application's controls changed while I was reading them. I've stopped; let the page settle before continuing.")
        except (ValueError, LookupError, PermissionError) as error:
            messages.append(str(error))
            if isinstance(error, (ValueError, LookupError)):
                context.clarification = {"request": text[:2000], "question": str(error)[:500]}
        finally:
            self.active.pop(chat_id, None)
            self.gates.pop(chat_id, None)
        return self.reply(chat_id, text, "\n\n".join(messages), append_user=False)

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
