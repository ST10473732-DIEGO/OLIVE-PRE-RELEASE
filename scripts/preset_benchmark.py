"""Bounded installed-model comparisons; never executes model code or tool calls."""
import asyncio
import ast
import json
from pathlib import Path
import re
import sys
import time
import tempfile
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.services.ollama_service import OllamaService
from olive.services.model_residency_service import ModelResidencyService
from olive.evaluation.model_fixtures import vision_image, TOOL_SCHEMA

CASES = [
    ("quick", "How many minutes are in two hours? Return only 120.", lambda r: r["content"].strip() == "120"),
    ("code_only", "Give only Python code for def square(x) returning x multiplied by itself. Do not create files or call tools.",
     lambda r: valid_square(r["content"])),
    ("csharp", "In C#, struct Counter { public int Value; } then var a = new Counter { Value = 1 }; var b = a; b.Value = 2; What does Console.WriteLine(a.Value + \",\" + b.Value) print? Reply only with the output.",
     lambda r: r["content"].strip().strip('`') == "1,2"),
    ("document", "Answer from these sources only: [D1 p2] 2024 sales were 12 units. [D2 p3] 2025 sales were 18 units. What is percentage growth? Reply exactly: 50% [D1 p2] [D2 p3]",
     lambda r: r["content"].strip() == "50% [D1 p2] [D2 p3]"),
    ("longer", "Return only a JSON array containing the squares of integers 0 through 39 in order.",
     lambda r: json.loads(r["content"].strip()) == [n*n for n in range(40)]),
    ("tool_proposal", "Use inspect_window to inspect Notepad. Do not type or click.",
     lambda r: len(r["tool_calls"]) == 1 and r["tool_calls"][0]["function"]["name"] == "inspect_window"
     and r["tool_calls"][0]["function"]["arguments"] == {"application": "Notepad"}),
]


def valid_square(text):
    text = re.sub(r"^```(?:python)?\s*|\s*```$", "", text.strip())
    tree = ast.parse(text)
    function = tree.body[0]
    return (len(tree.body) == 1 and isinstance(function, ast.FunctionDef) and function.name == "square" and
            len(function.body) == 1 and isinstance(function.body[0], ast.Return) and
            ast.dump(function.body[0].value) == ast.dump(ast.parse("x*x", mode="eval").body))


async def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="olive-benchmark-"))/"results.json"
    service = OllamaService()
    service.residency = ModelResidencyService(service)
    installed = {m.name: m for m in await service.list_models()}
    names = [n for n in ["qwen3:8b", "gpt-oss:20b", "qwen3-coder:30b", "devstral:24b", "qwen3-vl:8b"] if n in installed]
    records = []
    try:
        for name in names:
            cases = CASES if name != "qwen3-vl:8b" else [("vision", "Read the white button text in the image. Reply only SAVE.", lambda r: r["content"].strip() == "SAVE")]
            for phase in ("first_pass", "warm"):
                for label, prompt, check in cases:
                    record = {"model": name, "case": label, "phase": phase, "correct": False}
                    started = time.perf_counter()
                    before = await service.loaded_models()
                    record["resident_before"] = [m["name"] for m in before]
                    user = {"role": "user", "content": prompt}
                    if label == "vision": user["images"] = [vision_image()]
                    try:
                        result = await asyncio.wait_for(service.chat_measured(name, [user],
                            options={"temperature": 0, "num_ctx": 4096, "num_predict": 1200},
                            tools=TOOL_SCHEMA if label == "tool_proposal" else None,
                            think=None if label == "vision" else "low" if name.startswith("gpt-oss") else False,
                            stream=True), 75)
                        record.update(content=result["content"], tool_calls=result["tool_calls"],
                            first_content_ms=result["first_token_ms"], load_ms=result["load_duration"]/1e6,
                            done_reason=result.get("done_reason"))
                        record["correct"] = bool(check(result))
                    except Exception as error:
                        record["error"] = type(error).__name__
                    record["total_ms"] = round((time.perf_counter()-started)*1000, 1)
                    record["resident_after"] = await service.loaded_models()
                    record["system_ram_used"] = psutil.virtual_memory().used
                    records.append(record)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(json.dumps({"records": records, "note": "First pass is not guaranteed cold: resident_before/load_ms record actual state. Post-request RAM/VRAM samples are not peak utilization. Generated code is syntax/shape checked, not executed."}, indent=2))
                    print(name, label, phase, record["correct"], record["total_ms"], flush=True)
    finally:
        if service.residency.current:
            await service.unload_model(service.residency.current)
    print("Evidence:", target, flush=True)


if __name__ == "__main__": asyncio.run(main())
