import unittest

from olive.models import Chat
from olive.services.chat_service import ChatService


class DummyRAG:
    async def retrieve(self, *args, **kwargs):
        return []


class ChatServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_current_user_message_is_not_duplicated(self):
        chat = Chat(model="test")
        chat.add_message("user", "hello")
        service = ChatService(ollama=None, rag=DummyRAG())
        messages, _ = await service.build_messages(chat, "hello")
        user_messages = [m for m in messages if m["role"] == "user"]
        self.assertEqual(len(user_messages), 1)
        self.assertEqual(user_messages[0]["content"], "hello")


if __name__ == "__main__":
    unittest.main()
