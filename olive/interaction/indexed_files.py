"""Find existing indexed documents inside an authorized folder; never crawl content."""

import asyncio
from pathlib import Path
from ..agent.permission_service import PermissionDecision
from ..agent.tool_schema import ToolDefinition
from ..agent.tool_result import ToolResult


class IndexedFileSearchTool:
    def __init__(self, services):
        self.s = services
        self.definition = ToolDefinition("knowledge.find_files", "Find indexed files by topic in the selected folder",
            "knowledge", {"type": "object", "required": ["path", "chat_id", "query"]},
            required_permissions=("filesystem.read",), timeout_seconds=30)

    async def execute(self, arguments, context):
        root = Path(arguments["path"]).expanduser().resolve()
        chat = self.s.chats[arguments["chat_id"]]
        candidates = {}
        extension = arguments.get("extension", "").lstrip(".").casefold()
        eligible = []
        for ref in chat.documents:
            if not ref.original_path or not ref.indexed:
                continue
            path = Path(ref.original_path).resolve()
            if not path.is_relative_to(root) or (extension and path.suffix.casefold() != "." + extension):
                continue
            if self.s.permissions.evaluate("filesystem.read", str(path)).decision == PermissionDecision.DENY:
                continue
            eligible.append((ref.id, str(path)))
        candidates.update(eligible[:100])
        hits = await asyncio.to_thread(self.s.rag.store.lexical_search, chat.id, arguments["query"], 60, list(candidates))
        paths = list(dict.fromkeys(candidates[hit.document_id] for hit, _ in hits))
        return ToolResult(True, "Indexed topic candidates found", {
            "paths": paths[:30], "truncated": len(eligible) > 100 or len(hits) >= 60 or len(paths) > 30,
            "indexed_only": True})
