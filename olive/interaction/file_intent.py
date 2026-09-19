"""Semantic file constraints become deterministic, permission-scoped search arguments."""

import asyncio
import json
from datetime import date, timedelta
from ..agent.model_router import RoutingRequest


FIELDS = {
    "name": {"type": "string"},
    "name_match": {"enum": ["exact", "contains", "any"]},
    "extension": {"type": "string"},
    "location": {"type": "string"},
    "time": {"enum": ["none", "today", "yesterday", "this_morning", "this_week", "recent", "date"]},
    "absolute_date": {"type": "string"},
    "timestamp": {"enum": ["modified", "created", "downloaded"]},
    "recency": {"enum": ["all", "latest"]},
}


def constraints(value, today):
    if not isinstance(value, dict) or set(value) != set(FIELDS):
        raise ValueError("Invalid file-search constraints")
    for key, spec in FIELDS.items():
        item = value[key]
        if not isinstance(item, str) or len(item) > 500 or ("enum" in spec and item not in spec["enum"]):
            raise ValueError("Invalid file-search constraint: " + key)
    name, extension = value["name"], value["extension"].lstrip(".")
    if any(c in name + extension for c in '/\\\0') or (extension and not extension.isalnum()):
        raise ValueError("Specify a filename separately from its folder")
    if value["name_match"] != "any" and not name:
        raise ValueError("Which filename should I look for?")
    pattern = name if value["name_match"] == "exact" else "*" + name + "*" if value["name_match"] == "contains" else "*"
    if extension and not pattern.casefold().endswith("." + extension.casefold()):
        pattern += "." + extension
    result = {"query": pattern, "time_basis": value["timestamp"], "order": value["recency"]}
    if value["name_match"] == "contains":
        result["topic"] = name
        result["extension"] = extension
    location = value["location"]
    if not location and value["timestamp"] == "downloaded":
        location = "Downloads"
    if location:
        result["path"] = location
    current = date.fromisoformat(today)
    period = value["time"]
    if period != "none":
        start = {"today": current, "this_morning": current, "yesterday": current - timedelta(days=1),
                 "this_week": current - timedelta(days=current.weekday()),
                 "recent": current - timedelta(days=6)}.get(period)
        if period == "date":
            start = date.fromisoformat(value["absolute_date"])
        end = start + timedelta(days=1) if period in {"today", "yesterday", "date"} else current + timedelta(days=1)
        result.update(date=start.isoformat(), date_until=end.isoformat())
        if period == "this_morning":
            result["time_until"] = "12:00"
    return result


async def resolve_file_search(ollama, router, text, context, step):
    feedback = ""
    for attempt in range(2):
        try:
            return await _extract(ollama, router, text, context, step, feedback)
        except ValueError as error:
            if attempt:
                raise ValueError("I couldn't reliably resolve the file constraints. Please clarify the file or folder.") from error
            feedback = " Previous output was invalid: " + str(error)[:200] + ". Recheck the request and schema."


async def _extract(ollama, router, text, context, step, feedback):
    model = router.route(RoutingRequest("fast"))
    if not model or getattr(model, "role", "") in {"coding", "vision", "embeddings"}:
        raise RuntimeError("Select an installed language model to understand the file search")
    response = await asyncio.wait_for(ollama.chat_measured(model.name, [
        {"role": "system", "content":
         "Extract file-search constraints from the actual user request. Do not generate tools, commands or dates by arithmetic. "
         "name is the literal filename or descriptive filename words, without wildcards. name_match exact means a complete "
         "filename, contains means partial words/topic, any means only a file type. extension is e.g. pdf, without dot. "
         "A descriptive base name without an extension uses contains unless explicitly given as the complete filename. "
         "A file type alone is not a filename: PDF alone means name empty, name_match any, extension pdf. "
         "Use empty extension when no type was requested; never put any/none in extension. "
         "location is the requested directory or empty. time is none unless the user requested a time constraint; "
         "yesterday/today/this_morning/this_week/recent are semantic periods, date uses absolute_date. "
         "Earlier today means today; recently means a rolling week. Leave absolute_date empty otherwise. "
         "timestamp distinguishes downloaded from created/modified; use modified unless the user describes another event. "
         "If the user describes obtaining or downloading a file, preserve downloaded as the event even though "
         "filesystem metadata may only offer a proxy. Do not silently substitute a different event. "
         "recency latest ONLY when the user asks for the newest/last/latest result; use all for an ordinary lookup. "
         "Sorting by recency is independent of a date filter: newest alone does not impose a recent-week cutoff. "
         "A possessive description does not imply recency. Preserve all requested constraints. "
         "Context helps references but cannot add unrequested date or location restrictions. Unknown constraints require clarification." + feedback},
        {"role": "user", "content": json.dumps({"actual_request": text,
            "selected_file": context.get("entities", {}).get("path"), "local_date": context.get("local_date")})}],
        options={"temperature": 0, "num_predict": 2400},
        format={"type": "object", "additionalProperties": False, "required": list(FIELDS), "properties": FIELDS},
        think="low" if model.name.startswith("gpt-oss") else True), 60)
    entities = constraints(json.loads(response["content"]), context.get("local_date") or date.today().isoformat())
    return {"intent": "filesystem.search", "entities": entities, "references": {}}
