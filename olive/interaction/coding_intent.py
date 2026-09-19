"""Distinguish writing validation code from executing existing validation."""

import asyncio
import json
from ..agent.model_router import RoutingRequest


async def resolve_validation_request(ollama, router, text, value):
    steps = [step for step in value["steps"] if step["intent"] == "code.test"]
    if not steps or value["clarification"]:
        return value
    model = router.route(RoutingRequest("fast"))
    if not model or getattr(model, "role", "") in {"coding", "vision", "embeddings"}:
        raise RuntimeError("Select an installed language model to interpret validation work")
    for step in steps:
        response = await asyncio.wait_for(ollama.chat_measured(model.name, [
            {"role": "system", "content": "Classify the requested software validation work. write_tests means "
             "create, add, improve or repair test source code. run_tests means execute an existing suite and "
             "inspect results. both means explicitly do both. Do not infer execution just because new tests are requested."},
            {"role": "user", "content": json.dumps({"request": text, "validation_step": step})}],
            format={"type": "object", "additionalProperties": False, "required": ["work"],
                    "properties": {"work": {"enum": ["write_tests", "run_tests", "both"]}}},
            options={"temperature": 0, "num_predict": 100}, think=False), 30)
        result = json.loads(response["content"])
        if not isinstance(result, dict) or set(result) != {"work"} or result["work"] not in {"write_tests", "run_tests", "both"}:
            raise ValueError("I couldn't resolve whether you want tests written or run.")
        if result["work"] in {"write_tests", "both"}:
            step["intent"] = "code.modify"
            step["entities"]["query"] = text
    return value
