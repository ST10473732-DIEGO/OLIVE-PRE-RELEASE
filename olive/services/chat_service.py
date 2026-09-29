from __future__ import annotations

from typing import Any, AsyncIterator, TYPE_CHECKING

from ..models import Chat
from .context_service import ContextService
from .generation_pipeline import GenerationPipeline

if TYPE_CHECKING:
    from .generation_pipeline import PreparedGeneration
    from .ollama_service import OllamaService
    from .rag_service import RAGResult, RAGService


class ChatService:
    def __init__(self, ollama: "OllamaService", rag: "RAGService", context: ContextService | None = None, memory=None):
        self.ollama = ollama
        self.rag = rag
        self.context = context or ContextService()
        self.pipeline = GenerationPipeline(ollama, rag, memory=memory, context=self.context)

    async def build_messages(
        self,
        chat: Chat,
        user_text: str,
        image_base64: list[str] | None = None,
    ) -> tuple[list[dict[str, Any]], list["RAGResult"]]:
        prepared = await self.pipeline.prepare(chat, user_text, image_base64)
        return prepared.messages, prepared.rag_results

    async def stream_reply(
        self,
        chat: Chat,
        user_text: str,
        image_base64: list[str] | None = None,
        selected_document_id=None,
        observed_text='',
    ) -> tuple[AsyncIterator[str], "PreparedGeneration"]:
        return await self.pipeline.stream(chat, user_text, image_base64, selected_document_id, observed_text=observed_text)

    async def summarize(self, chat: Chat) -> str:
        if not chat.messages:
            return ""
        transcript = []
        for message in chat.messages:
            label = "User" if message.role == "user" else "Assistant"
            transcript.append(f"{label}: {message.content}")
        prompt = (
            "Summarise this conversation for future context. Preserve decisions, user preferences, "
            "important facts, unresolved tasks, and technical details. Do not add new information.\n\n"
            + "\n\n".join(transcript)
        )
        messages = [
            {"role": "system", "content": "You create compact, faithful conversation memory summaries."},
            {"role": "user", "content": prompt},
        ]
        return (await self.ollama.chat_once(chat.model, messages,
            options={"temperature": 0.2, "num_predict": 1400},
            **({"think": False} if chat.preset == "uncensored" else {}))).strip()
