"""Labelled isolated conversation variants; no model output or private data."""
from pathlib import Path
import os
import sys
import tempfile

if __name__ == '__main__':
    profile = Path(sys.argv[1]).resolve()
    if not profile.is_relative_to(Path(tempfile.gettempdir()).resolve()) or any(profile.iterdir()):
        raise SystemExit('Use an empty temporary fixture profile')
    os.environ['OLIVE_DATA_DIR'] = str(profile)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from olive.models import Chat
    from olive.storage.chat_repository import ChatRepository
    chat = Chat(title='Fixture conversation branches')
    chat.add_message('user','Find the uniquefixturemarker in this example.')
    chat.add_message('assistant','Fixture branch two.\n\n```python\nprint("Fixture only")\n```')
    chat.response_branches = {'0':['Fixture branch one.',chat.messages[-1].content]}
    chat.branch_index = {'0':1}
    other = Chat(title='Fixture retained conversation')
    ChatRepository(profile / 'chats.json').save_all([chat,other])
