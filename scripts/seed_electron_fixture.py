"""Explicit isolated demonstration data; refuses existing/non-temporary profiles."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('profile')
    args=parser.parse_args()
    profile=Path(args.profile).resolve()
    if not profile.is_relative_to(Path(tempfile.gettempdir()).resolve()) or any(profile.iterdir()):
        raise ValueError('Use an empty temporary profile for synthetic fixtures')
    os.environ['OLIVE_DATA_DIR']=str(profile)
    from olive.models import Chat
    from olive.storage.chat_repository import ChatRepository
    from olive.storage.workspace_repository import WorkspaceRepository
    from olive.workspace import Workspace
    workspace=profile/'fixture-workspace'
    workspace.mkdir()
    (workspace/'main.py').write_text('"""Isolated OLIVE demonstration project."""\n\ndef greeting(name):\n    return f"Hello, {name}!"\n\nif __name__ == "__main__":\n    print(greeting("OLIVE"))\n',encoding='utf-8')
    (workspace/'tests').mkdir()
    (workspace/'tests/test_main.py').write_text('import unittest\nfrom main import greeting\n\nclass GreetingTests(unittest.TestCase):\n    def test_greeting(self):\n        self.assertEqual(greeting("OLIVE"), "Hello, OLIVE!")\n',encoding='utf-8')
    record=Workspace(title='Fixture · local Python project',root_path=str(workspace),trust_level='approved')
    WorkspaceRepository(profile/'workspaces.json').save(record)
    chat=Chat(title='Fixture · a small Python idea',model='qwen3:8b')
    chat.add_message('user','Help me turn a small idea into a reliable Python function.')
    chat.add_message('assistant','Start with one clear behaviour and a test.\n\n```python\ndef greeting(name: str) -> str:\n    return f"Hello, {name}!"\n```\n\n| Next step | Purpose |\n| --- | --- |\n| Add a test | Define the expected result |\n| Run it locally | Observe what actually happens |\n\nThis is synthetic demonstration content, not a model response or execution result.')
    ChatRepository(profile/'chats.json').save_all([chat])
    print(json.dumps({'workspace_id':record.id,'chat_id':chat.id}))


if __name__=='__main__':
    main()
