"""Test-only inference engine. Real OllamaService filtering/residency surrounds it.

No production switch, environment variable or remote protocol can select it.
"""
import asyncio
from types import SimpleNamespace

from olive.application.chat_controller import ChatController
from olive.connect.inference_client import RemoteInferenceClient
from olive.models import Chat
from olive.services.model_registry import ModelCapabilityRegistry
from olive.services.model_residency_service import ModelResidencyService
from olive.services.ollama_service import OllamaService
from olive.services.presets import PRESETS, PresetCatalog
from olive.services.remote_inference_runtime import RemoteInferenceRuntime
from olive.storage.chat_repository import ChatRepository


class Engine:
    def __init__(self):
        self.names = {PRESETS[p]['model'] for p in ('fast', 'normal', 'max')}
        self.calls = []
        self.unloads = []
        self.mode = 'normal'
        self.started = asyncio.Event()
        self.stopped = asyncio.Event()
        self.release = asyncio.Event()
        self.cleanup_entered = asyncio.Event()
        self.cleanup_release = asyncio.Event()
        self.hold_cleanup = False
        self.parts = ['First visible delta. ' * 20, 'Second visible delta. ' * 20]

    async def list(self):
        return {'models': [{'model': name} for name in sorted(self.names)]}

    async def show(self, model):
        return {'capabilities': ['completion'], 'model_info': {'test.context_length': 8192}}

    async def ps(self):
        return {'models': []}

    async def generate(self, **kwargs):
        assert kwargs['keep_alive'] == 0
        self.unloads.append(kwargs['model'])

    async def pull(self, *args, **kwargs):
        raise AssertionError('A remote request must never install a model')

    async def chat(self, **kwargs):
        assert kwargs['tools'] == []
        assert kwargs['stream'] is True
        self.calls.append(kwargs)
        self.started.set()
        async def parts():
            try:
                if self.mode == 'delayed':
                    await self.release.wait()
                if self.mode == 'failure':
                    raise RuntimeError('private provider traceback /private/path secret=never-send')
                if self.mode == 'overflow':
                    yield {'message': {'content': 'x' * 65_000}}
                else:
                    for part in self.parts:
                        yield {'message': {'content': part, 'thinking': 'HIDDEN_REASONING_SECRET',
                                           'tool_calls': [{'function': {'name': 'shell'}}]}}
                        if self.mode == 'long':
                            await self.release.wait()
                    yield {'done': True, 'done_reason': 'length' if self.mode == 'token_limit' else 'stop',
                           'message': {'content': '', 'thinking': 'SECRET'}}
            finally:
                self.cleanup_entered.set()
                if self.hold_cleanup:
                    await self.cleanup_release.wait()
                self.stopped.set()
        return parts()


async def model_graph(connect, profile, *, engine=None, publish=lambda *args: None):
    engine = engine or Engine()
    ollama = OllamaService()
    ollama.client = engine
    ollama.residency = ModelResidencyService(ollama)
    registry = ModelCapabilityRegistry(ollama)
    await registry.refresh()
    repo = ChatRepository(profile / 'chats.json')
    s = SimpleNamespace(connect=connect, ollama=ollama, model_registry=registry,
        model_infos=await ollama.list_models(), chat_repo=repo, settings={}, publish=publish)
    s.presets = PresetCatalog(s)
    chat = Chat(preset='fast', model=PRESETS['fast']['model'])
    s.chats = {chat.id: chat}
    s.current_chat_id = chat.id
    s.save_chats = lambda: repo.save_all(s.chats.values())
    s.chat = ChatController(s)
    s.remote_inference = RemoteInferenceClient(connect)
    connect.attach_inference(RemoteInferenceRuntime(s.presets, ollama), asyncio.get_running_loop())
    return s, engine
