"""One canonical embedding default; lexical retrieval whenever it is not installed."""
import os
from pathlib import Path
import tempfile
import unittest

from olive import config
from olive.bridge.settings import FIELDS
from olive.models import Chat, DocumentRef
from olive.services.diagnostics_service import DiagnosticsService
from olive.services.document_service import ExtractedDocument
from olive.services.model_policy import CANDIDATES, DEFAULT_EMBEDDING_MODEL
from olive.services.model_registry import ModelCapabilityRegistry
from olive.services.ollama_service import ModelInfo
from olive.services.rag_service import RAGService
from olive.storage.rag_store import RAGStore
from olive.storage.settings_repository import SettingsRepository


class NoEmbeddingOllama:
    """Ollama with only a chat model: the default embedding model is absent."""

    def __init__(self):
        self.embedded = []
        self.pulled = []

    async def list_models(self):
        return [ModelInfo('qwen3:8b')]

    async def model_capabilities(self, name):
        return ('completion',)

    async def context_length(self, name):
        return 8192

    async def is_model_available(self, model):
        return False

    async def embed(self, model, texts):
        self.embedded.append(model)
        raise AssertionError('no embedding request without an installed model')

    async def pull(self, *args, **kwargs):
        self.pulled.append(args)
        raise AssertionError('retrieval must never download a model')

    async def ping(self):
        return True


class EmbeddingDefaultTests(unittest.IsolatedAsyncioTestCase):
    def test_one_default_across_config_policy_settings_and_schema(self):
        self.assertEqual(DEFAULT_EMBEDDING_MODEL, 'qwen3-embedding:0.6b')
        self.assertEqual(CANDIDATES['embedding'][0], DEFAULT_EMBEDDING_MODEL)
        self.assertEqual(config.EMBEDDING_MODEL, os.getenv('OLIVE_EMBEDDING_MODEL', DEFAULT_EMBEDDING_MODEL))
        schema = next(f for f in FIELDS if f['key'] == 'embedding_model')
        self.assertEqual(schema['default'], DEFAULT_EMBEDDING_MODEL)

    def test_settings_fill_missing_default_but_keep_a_stored_choice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = SettingsRepository(root / 'settings.json', root / 'defaults.json', root / 'aliases.json')
            self.assertEqual(repo.load()['embedding_model'], config.EMBEDDING_MODEL)
            (root / 'settings.json').write_text('{"embedding_model": "nomic-embed-text"}', encoding='utf-8')
            # Existing vectors were made by the stored model; a new default must not replace it.
            self.assertEqual(repo.load()['embedding_model'], 'nomic-embed-text')

    async def test_absent_default_model_keeps_lexical_retrieval_without_download_or_semantic_claim(self):
        ollama = NoEmbeddingOllama()
        registry = ModelCapabilityRegistry(ollama)
        await registry.refresh()
        self.assertIsNone(registry.select_embedding_model(DEFAULT_EMBEDDING_MODEL))
        with tempfile.TemporaryDirectory() as tmp:
            store = RAGStore(Path(tmp) / 'rag.sqlite3')
            rag = RAGService(store, ollama, DEFAULT_EMBEDDING_MODEL)
            ref = DocumentRef('doc', 'manual.txt')
            store.upsert_document('doc', 'chat', 'manual.txt', 'text', None, None)
            chunk = {'chat_id': 'chat', 'document_name': 'manual.txt', 'chunk_index': 0,
                     'page_number': None, 'content': 'hydraulic pump pressure troubleshooting'}
            indexed = await rag.index(ExtractedDocument(ref, [], [chunk]))
            self.assertTrue(indexed.indexed)
            self.assertFalse(indexed.embedding_indexed)
            results = await rag.retrieve('chat', 'hydraulic pump', limit=3)
            self.assertEqual([r.document_id for r in results], ['doc'])
            self.assertEqual(results[0].semantic_score, 0.0)
            self.assertGreater(results[0].lexical_score, 0)
            self.assertFalse(rag.last_diagnostics['semantic_enabled'])
            memory = type('Memory', (), {'list_all': lambda self: [],
                'repository': type('Repo', (), {'schema_version': lambda self: 1})()})()
            status = await DiagnosticsService(ollama, registry, rag, memory).collect(Chat(model='qwen3:8b'))
            self.assertEqual(status['active_embedding_model'], DEFAULT_EMBEDDING_MODEL)
            self.assertFalse(status['semantic_rag_enabled'])
        self.assertEqual(ollama.embedded, [])
        self.assertEqual(ollama.pulled, [])


if __name__ == '__main__':
    unittest.main()
