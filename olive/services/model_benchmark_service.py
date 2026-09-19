"""Opt-in installed-model measurements, with no execution of generated actions."""

import asyncio
from datetime import datetime, timezone
import json
import time
from ..storage.json_store import JsonStore
from ..evaluation.model_fixtures import GENERAL, CODING, TOOL_FIXTURE, TOOL_SCHEMA, schema, vision_image
from .model_policy import REQUEST_ROLE


class ModelBenchmarkService:
    def __init__(self, ollama, registry, path, emit=lambda *args: None):
        self.ollama, self.registry = ollama, registry
        self.store = JsonStore(path)
        self.emit = emit
        self.active = None
        self.cancelled = False

    def records(self):
        return self.store.read({"schema_version": 1, "records": []})["records"]

    def summary(self, model, role):
        group = "coding" if role == "coding" else "vision" if role == "vision" else "general"
        records = [r for r in self.records() if r["model"] == model and r["group"] == group]
        if not records:
            return None
        latest = records[-1]["run_id"]
        records = [r for r in records if r["run_id"] == latest]
        return {"quality": sum(r["success"] for r in records) / len(records),
                "latency_ms": sum(r["duration_ms"] for r in records) / len(records),
                "structured_success": sum(r["structured"] for r in records) / len(records),
                "last_benchmark": records[-1]["timestamp"], "samples": len(records)}

    def cancel(self):
        self.cancelled = True
        if self.active:
            self.active.cancel()

    async def run(self, models, timeout=60):
        if self.active:
            raise ValueError("A model benchmark is already active")
        if not isinstance(models, list) or not 1 <= len(models) <= 6 or not 5 <= timeout <= 180:
            raise ValueError("Choose 1-6 installed models and a bounded timeout")
        missing = [name for name in models if not self.registry.get(name)]
        if missing:
            raise ValueError("Benchmark models must already be installed: " + ", ".join(missing))
        self.active, self.cancelled = asyncio.current_task(), False
        run_id = datetime.now(timezone.utc).isoformat()
        results = []
        try:
            for name in dict.fromkeys(models):
                capability = self.registry.get(name)
                group = "vision" if capability.supports_vision else "coding" if capability.role == "coding" else "general"
                if capability.supports_embeddings:
                    continue
                fixtures = [("vision_button", "Read the button label. Return JSON with label in uppercase.", {"label": "SAVE"})] if group == "vision" else CODING if group == "coding" else GENERAL
                if group != "vision":
                    fixtures = [*fixtures, TOOL_FIXTURE]
                token = REQUEST_ROLE.set(group)
                try:
                    for fixture, prompt, expected in fixtures:
                        if self.cancelled:
                            break
                        self.emit("benchmark", {"model": name, "fixture": fixture, "status": "running"})
                        started = time.perf_counter()
                        record = {"run_id": run_id, "model": name, "group": group, "fixture": fixture,
                                  "timestamp": datetime.now(timezone.utc).isoformat(), "success": False,
                                  "structured": False, "duration_ms": 0, "error": ""}
                        message = {"role": "user", "content": prompt}
                        if group == "vision":
                            message["images"] = [vision_image()]
                        try:
                            response = await asyncio.wait_for(self.ollama.chat_measured(name, [message],
                                options={"temperature": 0, "num_predict": 512 if group == "vision" else 180,
                                         "num_ctx": 4096 if group == "vision" else 2048},
                                format=None if fixture == "tool_call" else schema(expected),
                                tools=TOOL_SCHEMA if fixture == "tool_call" else None,
                                think=None if group == "vision" else "low" if name.startswith("gpt-oss") else False, stream=True), timeout)
                            if fixture == "tool_call":
                                calls = response["tool_calls"]
                                function = calls[0]["function"] if len(calls) == 1 else {}
                                parsed = {"name": function.get("name"), "application": function.get("arguments", {}).get("application")}
                            else:
                                parsed = json.loads(response["content"])
                            record["structured"] = (isinstance(parsed, dict) and set(parsed) == set(expected)
                                and all(type(parsed[key]) is type(value) for key, value in expected.items()))
                            record["success"] = parsed == expected
                            record.update(load_ms=response["load_duration"] / 1e6,
                                          first_token_ms=response.get("first_token_ms"),
                                          tokens_per_second=response["eval_count"] / max(response["eval_duration"] / 1e9, 1e-9))
                        except asyncio.CancelledError:
                            record["error"] = "cancelled"
                            raise
                        except Exception as error:
                            record["error"] = type(error).__name__
                        finally:
                            record["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
                            self.store.write({"schema_version": 1, "records": [*self.records(), record][-500:]})
                            results.append(record)
                            self.emit("benchmark", record)
                finally:
                    REQUEST_ROLE.reset(token)
            return results
        finally:
            self.active = None
