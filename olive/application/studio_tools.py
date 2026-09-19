"""Explicit tools for native Studio operations, using the existing authorization boundary."""

import asyncio
import hashlib
from dataclasses import asdict

from ..agent.tool_schema import ToolDefinition
from ..agent.tool_result import ToolResult


class StudioAccessTool:
    def __init__(self, controller, action):
        self.controller, self.action = controller, action
        write = action in {"create", "save", "rollback", "rebase"}
        self.definition = ToolDefinition(
            f"studio.{action}",
            f"Studio {action}",
            "studio",
            {"type": "object", "required": ["workspace"]},
            risk_level="medium" if write else "low",
            required_permissions=("filesystem.write" if write else "filesystem.read",),
            confirmation_required=write,
            timeout_seconds=60,
        )

    async def execute(self, arguments, context):
        return await asyncio.to_thread(self.perform, arguments, context)

    def perform(self, arguments, context):
        service = self.controller.service(arguments["workspace"])
        action = self.action
        if action == "tree":
            data = {"entries": service.tree()}
        elif action == 'create':
            from ..services.editing_service import EditingService
            service.checkpoints.create(service.workspace, context.task_id, [arguments['path']])
            EditingService(service.workspace).create_file(arguments['path'], '', context.task_id)
            data = asdict(service.open_file(arguments['path']))
        elif action == "open":
            state = service.open_files.get(arguments["path"]) or service.open_file(arguments["path"])
            data = asdict(state)
        elif action == "save":
            path = arguments["path"]
            state = service.open_files[path]
            if arguments["expected_hash"] != state.loaded_hash:
                raise RuntimeError("Editor version changed; reload before saving")
            if "expected_text" in arguments and arguments["expected_text"] != state.text:
                raise RuntimeError("Editor content changed while the proposed edit was awaiting approval")
            service.update(path, arguments["text"])
            service.save(path, context.task_id)
            data = asdict(state)
        elif action == "search":
            data = {"matches": service.search_workspace(arguments["query"])}
        elif action in {"compare", "rebase"}:
            path = arguments['path']
            state = service.open_files[path]
            with service.workspace.resolve(path).open('rb') as handle:
                raw = handle.read(400_001)
            if len(raw) > 400_000 or b'\0' in raw:
                raise ValueError('This disk version exceeds comparison bounds')
            disk_text = raw.decode('utf-8')
            disk_hash = hashlib.sha256(raw).hexdigest()
            if action == 'rebase':
                if arguments['disk_hash'] != disk_hash or arguments['expected_hash'] != state.loaded_hash:
                    raise RuntimeError('The compared version changed; compare again')
                # Explicit reviewed base change only. The actual write still requires save approval.
                state.loaded_hash = disk_hash
                state.saved_text = disk_text
            data = {'disk_text': disk_text, 'disk_hash': disk_hash, 'loaded_hash': state.loaded_hash}
        elif action == "rollback":
            data = {"files": self.controller.s.checkpoints.rollback(service.workspace, arguments["task_id"])}
        else:
            raise ValueError("Unknown Studio operation")
        return ToolResult(True, f"Studio {action} completed", data)
