"""Bounded local schema diagnostic using only the owned acceptance image."""
import asyncio
import base64
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.services.ollama_service import OllamaService
from olive.services.model_residency_service import ModelResidencyService


async def main():
    image = Path(__file__).resolve().parents[1] / ".qt-smoke" / "visual-fixture.png"
    service = OllamaService()
    service.residency = ModelResidencyService(service)
    schema = {"type": "object", "additionalProperties": False, "required": ["bounding_box"], "properties": {
        "bounding_box": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4}}}
    state = "--state" in sys.argv
    if state:
        schema = {"type": "object", "additionalProperties": False, "required": ["label"], "properties": {"label": {"type": "string"}}}
    try:
        response = await asyncio.wait_for(service.chat_measured("qwen3-vl:8b", [{"role": "user",
            "content": 'Read the button label. Return JSON with label in uppercase.' if state else 'Locate the blue Preview button. Return only JSON {"bounding_box": [left, top, right, bottom]} in pixels of this 500 by 240 image.',
            "images": [base64.b64encode(image.read_bytes()).decode()]}],
            options={"temperature": 0, "num_predict": 600, "num_ctx": 4096},
            format=schema if "--schema" in sys.argv or state else None,
            think=None if "--default-thinking" in sys.argv else False, stream=True), 35)
        print(json.dumps({"content": response["content"][:1000], "tokens": response["eval_count"], "duration_ms": response["duration_ms"],
                          "thinking_characters": response["thinking_characters"], "done_reason": response["done_reason"]}), flush=True)
    finally:
        await service.unload_model("qwen3-vl:8b")


if __name__ == "__main__":
    asyncio.run(main())
