"""Opt-in public-web and installed-Ollama smoke test using disposable data only."""

import asyncio
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse


async def main():
    with tempfile.TemporaryDirectory(prefix="olive-research-smoke-") as directory:

        async def confirm(request):
            # This opt-in test authorizes only the named harmless research actions.
            return ConfirmationResponse(request.tool_name in {"web.search", "web.open", "web.learn_urls"})

        def event(topic, value):
            if topic == "research":
                print(value["status"], value.get("activity", ""), flush=True)

        services = ServiceContainer(event, confirm, Path(directory), migrate=False)
        try:
            await services.initialize()
            services.settings["research"] = {
                "max_searches": 1,
                "max_pages": 2,
                "max_link_depth": 0,
                "timeout": 600,
                "browser_provider": "http",
                "depth": "Quick",
            }
            result = await services.research.start(
                question="Research Ollama embeddings using site:docs.ollama.com and read https://docs.ollama.com/capabilities/embeddings . Explain text embedding briefly."
            )
            print(
                json.dumps(
                    {
                        "research_status": result["status"],
                        "error": result["error"],
                        "sources": len(result["sources"]),
                        "evidence": len(result["evidence"]),
                        "queries": result["queries"],
                        "report": result["final_report"],
                    },
                    indent=2,
                ),
                flush=True,
            )
            learned = await services.research.learn_urls(
                ["https://docs.ollama.com/capabilities/embeddings"], collection="Temporary smoke"
            )
            record = learned["results"][0]
            if record["status"] == "failed":
                raise RuntimeError(record["error"])
            source = record["source"]
            hits = await services.research.web_knowledge.retrieve("embedding text vectors")
            assert any(hit["source"]["id"] == source["id"] for hit in hits)
            source_id, expected_hash = source["id"], source["content_hash"]
            embedding_model = services.rag.embedding_model
        finally:
            await services.shutdown()
        restored = ServiceContainer(lambda *args: None, confirm, Path(directory), migrate=False)
        try:
            page = restored.research.web_knowledge.page(source_id)
            assert page.content_hash == expected_hash
            assert restored.research.sources.load_all()[source_id].url == page.url
            hits = await restored.research.web_knowledge.retrieve("embedding text vectors")
            assert any(hit["source"]["id"] == source_id for hit in hits)
            print(
                json.dumps(
                    {
                        "learning": "passed",
                        "restart_provenance": "passed",
                        "embedding_model": embedding_model,
                        "content_hash": expected_hash,
                    }
                ),
                flush=True,
            )
        finally:
            await restored.shutdown()
        if result["status"] != "completed":
            raise RuntimeError("Live synthesis did not complete; see preserved status above")


if __name__ == "__main__":
    asyncio.run(main())
