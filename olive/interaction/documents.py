"""Temporary document reading through the existing tool permission boundary."""

from ..agent.tool_schema import ToolDefinition
from ..agent.tool_result import ToolResult


class SelectedDocumentTool:
    def __init__(self, services):
        self.s = services
        self.definition = ToolDefinition("knowledge.read_selected", "Read a selected document for this conversation",
            "knowledge", {"type": "object", "required": ["path", "chat_id"]},
            required_permissions=("filesystem.read",), timeout_seconds=180)

    async def execute(self, arguments, context):
        if arguments["chat_id"] not in self.s.chats:
            raise ValueError("Unknown conversation")
        await self.s.knowledge.attach(arguments["chat_id"], [arguments["path"]], permanent=False)
        from pathlib import Path
        refs = [ref for ref in self.s.chats[arguments["chat_id"]].documents
                if ref.original_path and Path(ref.original_path).resolve() == Path(arguments["path"]).resolve()]
        if len(refs) != 1 or not refs[0].indexed:
            raise ValueError("The selected document has not been indexed successfully")
        return ToolResult(True, "The document is available for temporary retrieval", {"ready": True, "document_id": refs[0].id})


class ProjectDocumentTool:
    def __init__(self, services):
        self.s = services
        self.definition = ToolDefinition("knowledge.add_to_project", "Add the selected document to project Knowledge",
            "knowledge", {"type": "object", "required": ["path", "chat_id", "project_id"]},
            required_permissions=("filesystem.read", "knowledge.write"), timeout_seconds=180)

    async def execute(self, arguments, context):
        from pathlib import Path
        project = self.s.project_repo.load_all()[arguments["project_id"]]
        chat = self.s.chats[arguments["chat_id"]]
        await self.s.knowledge.attach(chat.id, [arguments["path"]], permanent=True)
        refs = [ref for ref in chat.documents if ref.original_path and
                Path(ref.original_path).resolve() == Path(arguments["path"]).resolve()]
        if len(refs) != 1 or not refs[0].indexed:
            raise ValueError("The selected document could not be indexed for the project")
        refs[0].temporary = False
        if refs[0].id not in project.knowledge_ids:
            project.knowledge_ids.append(refs[0].id)
        self.s.project_repo.save(project)
        self.s.save_chats()
        return ToolResult(True, "Document added to project Knowledge", {"document_id": refs[0].id, "project": project.title})
