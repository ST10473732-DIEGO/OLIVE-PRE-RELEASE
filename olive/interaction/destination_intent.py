"""Generic hierarchy/address extraction, separate from application discovery."""

import asyncio
import json
from ..agent.model_router import RoutingRequest


async def preserve_destination(ollama, router, text, value):
    steps = value["steps"]
    applications = {s["entities"]["application"].casefold() for s in steps if s["entities"].get("application")}
    if len(applications) > 1:
        return value
    if value["clarification"] or not any(s["entities"].get("server") or s["entities"].get("channel") for s in steps):
        return value
    model = router.route(RoutingRequest("reasoning"))
    if not model or getattr(model, "role", "") in {"coding", "vision", "embeddings"}:
        raise ValueError("Select an installed language model to resolve the destination")
    fields = ("server", "channel", "recipient")
    response = await asyncio.wait_for(ollama.chat_measured(model.name, [
        {"role": "system", "content": "Extract explicitly named communication destinations from this user request. "
         "server is the community/workspace name; channel is a named room within it; recipient is a person or address. "
         "Never copy a server or channel into recipient. Keep names separate from words describing their kind. "
         "The application name is NOT a server. An abbreviated hierarchy can name a server followed by its channel "
         "without the words server or channel; resolve these two levels separately from the application. "
         "Optional # before a channel is not part of its name. Use empty string for absent fields. "
         "Preserve literal name words. Do not execute anything. Return only the schema."},
        {"role": "user", "content": json.dumps({"request": text, "application_names": sorted(applications)})}],
        format={"type": "object", "additionalProperties": False, "required": list(fields),
                "properties": {key: {"type": "string"} for key in fields}},
        options={"temperature": 0, "num_predict": 1600},
        think="low" if model.name.startswith("gpt-oss") else False), 90)
    destination = json.loads(response["content"])
    if not isinstance(destination, dict) or set(destination) != set(fields) or any(
            not isinstance(v, str) or len(v) > 200 or (v and v.casefold() not in text.casefold()) for v in destination.values()):
        raise ValueError("Please clarify the requested server, channel or recipient.")
    if destination["server"].casefold() in applications:
        raise ValueError("Which server within the application do you mean?")
    # Multiple distinct destinations need the original per-step interpretation.
    for key in fields:
        named = {s["entities"][key].casefold() for s in steps if s["entities"].get(key)}
        if len(named) > 1:
            return value
    for step in steps:
        if step["intent"] not in {"application.navigate", "communication.compose", "communication.send"}:
            continue
        for key in ("server", "channel"):
            if destination[key]:
                step["entities"][key] = destination[key]
                step["references"].pop(key, None)
        if step["intent"].startswith("communication."):
            if destination["recipient"]:
                step["entities"]["recipient"] = destination["recipient"]
            elif step["entities"].get("recipient") in {destination["server"], destination["channel"]}:
                step["entities"].pop("recipient", None)
    return value
