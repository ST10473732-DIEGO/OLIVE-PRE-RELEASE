"""Bounded diagnosis using a synthetic image; never print model reasoning."""
import asyncio
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.services.ollama_service import OllamaService
from olive.evaluation.model_fixtures import vision_image, schema


async def main():
    service = OllamaService()
    try:
        for structured, thinking in ((False, None), (True, None), (True, False)):
            response = await asyncio.wait_for(service.chat_measured("qwen3-vl:8b",
                [{"role": "user", "content": "Read the button label. Return JSON with label.", "images": [vision_image()]}],
                options={"temperature": 0, "num_predict": 256, "num_ctx": 4096},
                format=schema({"label": "SAVE"}) if structured else None, think=thinking), 60)
            content = response["content"]
            print(json.dumps({"structured": structured, "think_override": thinking, "content_length": len(content),
                              "content_prefix": content[:150], "tokens": response["eval_count"]}), flush=True)
    finally:
        await service.unload_model("qwen3-vl:8b")


asyncio.run(main())
