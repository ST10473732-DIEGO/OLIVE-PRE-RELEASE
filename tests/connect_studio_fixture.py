"""Owned fixture files with the real Studio controllers and process providers."""
from pathlib import Path
from types import SimpleNamespace
import asyncio
from olive.agent.permission_service import PermissionService
from olive.agent.tool_registry import ToolRegistry
from olive.application.studio_controller import StudioController
from olive.connect.studio_runtime import StudioRuntime
from olive.services.checkpoint_service import CheckpointService
from olive.services.run_service import RunService
from olive.services.workspace_service import WorkspaceService
from olive.storage.workspace_repository import WorkspaceRepository
from olive.studio_tooling.controller import StudioToolingController


def graph(connect, profile):
    profile = Path(profile)
    s = SimpleNamespace(data_dir=profile, connect=connect, publish=lambda *a: None,
        workspace_repo=WorkspaceRepository(profile / 'workspaces.json'),
        checkpoints=CheckpointService(profile / 'checkpoints'),
        permissions=PermissionService(profile / 'permissions.json'),
        tool_registry=ToolRegistry(), run_service=RunService())
    s.studio = StudioController(s)
    s.studio_tooling = StudioToolingController(s)
    connect.attach_studio(StudioRuntime(s), asyncio.get_running_loop())
    root = profile / 'fixture'
    root.mkdir(exist_ok=True)
    (root / 'main.py').write_text('import sys\nprint("warning", file=sys.stderr)\nprint("REMOTE OK")\n', encoding='utf-8')
    (root / 'tests').mkdir(exist_ok=True)
    (root / 'tests' / 'test_example.py').write_text('import unittest\nclass Example(unittest.TestCase):\n def test_ok(self): self.assertEqual(2 + 2, 4)\n', encoding='utf-8')
    workspace = WorkspaceService(s.workspace_repo).create('Fixture', root)
    return s, workspace
