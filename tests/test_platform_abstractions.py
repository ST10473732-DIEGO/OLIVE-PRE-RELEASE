import tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from olive.agent.fast_path import FastPathService
from olive.agent.model_router import ModelRouter, RoutingRequest
from olive.agent.tool_registry import ToolRegistry
from olive.agent.tool_result import ToolResult
from olive.agent.tool_schema import ToolContext, ToolDefinition
from olive.knowledge.learning_service import LearningService
from olive.knowledge.source import KnowledgeSource, SourceProvenance
from olive.knowledge.training_store import TrainingExampleStore
from olive.storage.knowledge_source_repository import KnowledgeSourceRepository
from olive.tools.host import InProcessToolHost

class Echo:
    definition=ToolDefinition("test.echo","echo","test",{})
    async def execute(self,args,context): return ToolResult(True,"ok",args)
class PlatformTests(unittest.IsolatedAsyncioTestCase):
    async def test_fast_path_math_and_tool_host(self):
        self.assertEqual(FastPathService().resolve("What is 15 * 27?").answer,"405")
        self.assertEqual(FastPathService().resolve("Show my Downloads folder").action.tool_name,"system.open_path")
        self.assertEqual(FastPathService().resolve("Create a folder named Test on my Desktop").action.tool_name,"filesystem.create_directory")
        self.assertEqual(FastPathService().resolve("Close Discord").action.tool_name,"system.close_application")
        self.assertEqual(FastPathService().resolve("Terminate Discord").action.tool_name,"system.terminate_application")
        self.assertEqual(FastPathService().resolve("Force close Chrome").action.tool_name,"system.terminate_application")
        registry=ToolRegistry(); registry.register(Echo()); result=await InProcessToolHost(registry).execute("test.echo",{"x":1},ToolContext("t")); self.assertTrue(result.success)
    async def test_model_router_roles_and_fallback(self):
        models={"small":SimpleNamespace(name="small",role="fast",context_length=8192,size=1,supports_embeddings=False,supports_vision=False),
                "embed":SimpleNamespace(name="embed",role="embedding",context_length=8192,size=1,supports_embeddings=True,supports_vision=False)}
        router=ModelRouter(SimpleNamespace(models=models)); self.assertEqual(router.route(RoutingRequest("fast",prefer_low_latency=True)).name,"small")
        self.assertEqual(router.route(RoutingRequest("embedding")).name,"embed")
    async def test_knowledge_and_training_require_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=KnowledgeSourceRepository(Path(tmp)/"sources.json"); learning=LearningService(repo)
            source=KnowledgeSource("pdf","Guide",SourceProvenance("local_document","C:/example.pdf"),"hash")
            with self.assertRaises(PermissionError): learning.add_approved_source(source,approved=False)
            learning.add_approved_source(source,approved=True); self.assertIn(source.id,repo.load_all())
            training=TrainingExampleStore(Path(tmp)/"training.json")
            with self.assertRaises(PermissionError): training.add("p","r",approved=False)
