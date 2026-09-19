"""Conversation coordination independent of desktop widgets."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from copy import deepcopy
import time

from ..models import Chat


class ChatController:
    def __init__(self, services):
        self.s = services
        self.generations = {}
        self.partials = {}
        self.images = {}
        self.suggestions = {}

    def list(self):
        return [
            {"id": c.id, "title": c.title, "model": c.model, "project_id": c.project_id}
            for c in sorted(self.s.chats.values(), key=lambda c: c.updated_at, reverse=True)
        ]

    def get(self, chat_id=None):
        chat = self.s.chats[chat_id or self.s.current_chat_id]
        value = chat.to_dict()
        value["documents"] = [ref.to_dict() for ref in chat.documents]
        value["generating"] = chat.id in self.generations
        value["partial"] = self.partials.get(chat.id, "")
        value["images"] = [{"name": name} for name, _ in self.images.get(chat.id, [])]
        interaction = getattr(self.s, "interaction", None)
        context = interaction.contexts.get(chat.id) if interaction else None
        value["pending_draft"] = deepcopy(context.pending) if context else None
        value['native_proposals']=[{'id':p['id'],'revision':p['revision'],'method':p['method'],'body':deepcopy(p['body'])} for p in context.personal_pending.values()] if context else []
        return value

    def new(self):
        chat = Chat()
        self.s.presets.apply(chat, "normal")
        self.s.chats[chat.id] = chat
        self.s.current_chat_id = chat.id
        self.s.save_chats()
        return self.get(chat.id)

    def select(self, chat_id):
        self.s.current_chat_id = chat_id
        return self.get(chat_id)

    def update(self, chat_id, **values):
        chat = self.s.chats[chat_id]
        if chat_id in self.generations:
            raise ValueError("Wait for generation to finish before changing this conversation")
        for name in ("title", "notes", "project_id", "system_prompt", "summary"):
            if name in values:
                setattr(chat, name, values[name])
        if "model" in values:
            chat.model = values["model"]
            chat.preset = ""
            chat.params.update(self.s.model_defaults.get(chat.model, {}))
        if "preset" in values:
            self.s.presets.apply(chat, values["preset"])
        chat.touch()
        self.s.save_chats()
        return self.get(chat_id)

    def save_draft(self, chat_id, text):
        """Persist unsent composer text separately from messages and pending actions."""
        if not isinstance(text, str) or len(text) > 32000:
            raise ValueError("Draft text must be at most 32,000 characters")
        chat = self.s.chats[chat_id]
        chat.draft = text
        chat.touch()
        self.s.save_chats()
        return {"chat_id": chat_id, "saved": True}

    def delete(self, chat_id):
        interaction = getattr(self.s, "interaction", None)
        if interaction and (chat_id in interaction.active or interaction.interpreting.get(chat_id)):
            raise ValueError("Stop this conversation's active request before deleting it")
        if chat_id in self.generations:
            raise ValueError("Stop generation before deleting this conversation")
        if len(self.s.chats) <= 1:
            raise ValueError("Keep at least one conversation")
        for ref in self.s.chats[chat_id].documents:
            self.s.rag.delete_document(ref.id)
        del self.s.chats[chat_id]
        self.images.pop(chat_id, None)
        self.s.current_chat_id = next(iter(self.s.chats))
        self.s.save_chats()
        return self.get()

    def stop(self, chat_id):
        task = self.generations.get(chat_id)
        if task:
            task.cancel()

    def stop_all(self):
        for task in list(self.generations.values()):
            task.cancel()

    async def send(self, chat_id, text="", regenerate=False, selected_document_id=None):
        if chat_id in self.generations:
            raise ValueError("This conversation is already generating")
        chat = self.s.chats[chat_id]
        images = [data for _, data in self.images.get(chat_id, [])]
        try:
            if any(not ref.indexed for ref in chat.documents):
                raise ValueError("Wait for attached documents to finish indexing, or remove failed attachments")
            self.s.presets.require(chat)
            if not chat.model:
                raise ValueError("Select an installed Ollama chat model first")
            if images and chat.preset != "deep" and not await self.s.ollama.is_vision_model(chat.model):
                raise ValueError("Choose a vision-capable model before sending images")
        except ValueError:
            if not regenerate and text.strip():
                chat.add_message("user", text.strip())
                self.s.save_chats()
                self.s.publish("chat", self.get(chat_id))
            raise
        # Vision discovery yields to the runtime; another send may have started.
        if chat_id in self.generations:
            raise ValueError("This conversation is already generating")
        previous = None
        if regenerate:
            if (
                len(chat.messages) < 2
                or chat.messages[-1].role != "assistant"
                or chat.messages[-2].role != "user"
            ):
                raise ValueError("No answer is available to regenerate")
            previous = chat.messages.pop()
            text = chat.messages[-1].content
        else:
            text = text.strip()
            if not text:
                raise ValueError("Enter a message")
            if not chat.messages:
                chat.title = text[:48]
            chat.add_message("user", text)
        user_index = len(chat.messages) - 1
        self.generations[chat_id] = asyncio.current_task()
        self.s.save_chats()
        self.s.publish("chat", self.get(chat_id))
        full = ""
        prepared = None
        stream = None
        completed = False
        try:
            selection = {"selected_document_id": selected_document_id} if selected_document_id else {}
            stream, prepared = await self.s.chat_service.stream_reply(chat, text, image_base64=images, **selection)
            last_emit = 0.0
            async for token in stream:
                full += token
                self.partials[chat_id] = full
                if time.monotonic() - last_emit >= 0.05:
                    self.s.publish("chat_stream", {"chat_id": chat_id, "text": full})
                    last_emit = time.monotonic()
            completed = True
        except asyncio.CancelledError:
            self.s.publish("notification", {"kind": "info", "message": "Generation stopped"})
        finally:
            if stream and hasattr(stream, "aclose"):
                await stream.aclose()
            if full.strip() and prepared:
                final = full.strip()
                message = chat.add_message(
                    "assistant",
                    final,
                    sources=[r.source_dict() for r in prepared.rag_results],
                    memory_ids=[m.id for m in prepared.memories],
                    grounding=self.s.grounding.analyze(final, prepared.rag_results).to_dict(),
                )
                message.completion_state = "complete" if completed else "incomplete"
                info = next((m for m in self.s.model_infos if m.name == chat.model), None)
                message.provider = {"runtime": "Ollama", "model": chat.model,
                                    "digest": getattr(info, "digest", ""), "preset": chat.preset}
                branches = chat.response_branches.setdefault(str(user_index), [])
                for value in ([previous.content] if previous else []) + [final]:
                    if value not in branches:
                        branches.append(value)
                chat.branch_index[str(user_index)] = len(branches) - 1
            elif previous:
                chat.messages.append(previous)
            self.images.pop(chat_id, None)
            for ref in list(chat.documents):
                if ref.temporary:
                    self.s.rag.delete_document(ref.id)
                    chat.documents.remove(ref)
            self.generations.pop(chat_id, None)
            self.partials.pop(chat_id, None)
            self.s.save_chats()
            self.s.publish("chat", self.get(chat_id))
        if not regenerate and self.s.settings.get("automatic_memory_suggestions", True):
            proposals = self.s.memory_suggestions.suggest(
                text, chat.id, user_index, chat.messages[user_index].id
            )
            if not proposals and self.s.settings.get("memory_model_extraction", False):
                proposals = await self.s.memory_suggestions.propose_structured(
                    text, chat.model, chat.id, chat.messages[user_index].id, user_index
                )
            for suggestion in proposals:
                if self.s.settings.get("auto_memory_approval", False):
                    self.s.memory_suggestions.approve(suggestion)
                else:
                    self.suggestions[suggestion.id] = suggestion
                    self.s.publish("memory_suggestion", asdict(suggestion))
        return self.get(chat_id)

    def branch(self, chat_id, user_index, direction=1):
        chat = self.s.chats[chat_id]
        if chat_id in self.generations:
            raise ValueError("Stop generation before changing branches")
        key = str(user_index)
        branches = chat.response_branches.get(key, [])
        if branches and user_index + 1 < len(chat.messages):
            index = (chat.branch_index.get(key, len(branches) - 1) + direction) % len(branches)
            chat.messages[user_index + 1].content = branches[index]
            # Legacy branch storage contains answer text only, not per-branch provenance.
            chat.messages[user_index + 1].sources = []
            chat.messages[user_index + 1].memory_ids = []
            chat.messages[user_index + 1].grounding = None
            chat.messages[user_index + 1].completion_state = "unverified"
            chat.branch_index[key] = index
            self.s.save_chats()
        return self.get(chat_id)

    async def summarize(self, chat_id):
        chat = self.s.chats[chat_id]
        summary = await self.s.chat_service.summarize(chat)
        chat.summary = summary
        chat.summary_message_count = len(chat.messages)
        self.s.save_chats()
        return summary

    def remove_image(self, chat_id, index):
        self.images.get(chat_id, []).pop(index)
        return self.get(chat_id)
