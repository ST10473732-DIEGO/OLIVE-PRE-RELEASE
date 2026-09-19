"""Field-scoped pending-action interpretation, with no execution or authorization."""

import asyncio
import json
from ..agent.model_router import RoutingRequest


async def pending_request(ollama, router, text, pending, role="fast"):
    model = router.route(RoutingRequest(role))
    if not model or getattr(model, "role", "") in {"coding", "vision", "embeddings"}:
        raise RuntimeError("Select an installed language model to understand the pending action")
    operations = ["revise", "cancel", "hold", "resume", "repeat", "submit", "unrelated"]
    disposition = await asyncio.wait_for(ollama.chat_measured(model.name, [
        {"role": "system", "content":
         "Classify the user's current request relative to one unsent message. Do not extract message text yet. "
         "revise = replace draft wording or destination; cancel = withdraw the request or discard it; "
         "hold = retain the draft without delivery or temporarily wait; resume = continue paused work; "
         "repeat = perform the previous task again from its beginning, not continue where it paused; "
         "submit = request actual delivery, still requiring separate confirmation; unrelated = another task "
         "or an informational question. An idiomatic withdrawal is cancel, not replacement message content. "
         "A correction changes what the draft will say and does not request delivery. Keeping a draft is hold. "
         "The presence of a recipient in background data never supplies a request to deliver."},
        {"role": "user", "content": json.dumps({"unsent_draft": pending.get("entities", {}), "new_request": text})}],
        format={"type": "object", "additionalProperties": False, "required": ["operation"],
                "properties": {"operation": {"enum": operations}}},
        options={"temperature": 0, "num_predict": 1000 if role == "reasoning" else 100},
        think="low" if model.name.startswith("gpt-oss") else False), 45)
    decision = json.loads(disposition["content"])
    if not isinstance(decision, dict) or set(decision) != {"operation"} or decision["operation"] not in operations:
        raise ValueError("Please clarify what should happen to the unsent message")
    operation = decision["operation"]
    if operation == "submit" and role == "fast":
        return await pending_request(ollama, router, text, pending, role="reasoning")
    if operation == "unrelated":
        return None
    if operation not in {"revise", "submit"}:
        return {"confidence": 1., "clarification": "", "steps": [{
            "intent": "task." + {"cancel": "cancel", "hold": "pause", "resume": "resume", "repeat": "repeat"}[operation],
            "entities": {}, "references": {}}]}
    fields = ["message", "subject", "recipient", "server", "channel", "application", "path"]
    schema = {"type": "object", "additionalProperties": False,
              "required": ["operation", "updates"], "properties": {
                  "operation": {"enum": [operation]},
                  "updates": {"type": "array", "maxItems": 7, "items": {
                      "type": "object", "additionalProperties": False, "required": ["field", "value"],
                      "properties": {"field": {"enum": fields}, "value": {"type": "string"}}}}}}
    result = await asyncio.wait_for(ollama.chat_measured(model.name, [
        {"role": "system", "content":
         "There is one UNSENT draft. The requested operation has already been classified as " + operation + ". "
         "Extract only the literal changed fields in the user's current request. "
         "Message content excludes the action verb, addressee, introductory correction instruction and quote delimiters. "
         "Retain all words and punctuation inside the requested message. "
         "Correcting what to say changes MESSAGE, not subject or recipient. Audience words within a greeting "
         "are message content. Preserve the entire replacement wording literally. Do not copy unchanged fields. "
         "Change destination only if the user changes who/where. Do not change the classified operation. All updates must be literal "
         "substrings of the new request. This output cannot approve or perform sending."},
        {"role": "user", "content": json.dumps({"unsent_draft": pending.get("entities", {}), "new_request": text})}],
        options={"temperature": 0, "num_predict": 2400}, format=schema,
        think="low" if model.name.startswith("gpt-oss") else True), 60)
    value = json.loads(result["content"])
    if (not isinstance(value, dict) or set(value) != {"operation", "updates"}
            or value["operation"] not in operations or not isinstance(value["updates"], list)
            or len(value["updates"]) > 7):
        raise ValueError("Please clarify the change to the pending message")
    updates = {}
    for update in value["updates"]:
        if (not isinstance(update, dict) or set(update) != {"field", "value"}
                or update["field"] not in fields or update["field"] in updates
                or not isinstance(update["value"], str) or not update["value"]
                or len(update["value"]) > 4000 or update["value"] not in text):
            raise ValueError("The proposed draft change did not preserve your wording")
        updates[update["field"]] = update["value"]
    operation = value["operation"]
    if operation != decision["operation"]:
        raise ValueError("Draft field extraction cannot change the requested operation")
    if operation == "revise" and updates.get("message", "").strip() == text.strip():
        # A copied whole utterance may conflate the speech act with its payload.
        # Resolve that boundary only; do not re-extract already separated fields.
        updates["message"] = await replacement_wording(ollama, model, text, pending)
    if operation == "unrelated":
        return None
    if operation not in {"revise", "submit"} and updates:
        raise ValueError("A task-control request cannot also change the message")
    intent = {"revise": "task.correct", "cancel": "task.cancel", "hold": "task.pause", "resume": "task.resume", "submit": "communication.send"}[operation]
    return {"confidence": 1., "clarification": "What should I change?" if operation == "revise" and not updates else "",
            "steps": [{"intent": intent, "entities": updates, "references": {}}]}


async def replacement_wording(ollama, model, text, pending):
    result = await asyncio.wait_for(ollama.chat_measured(model.name, [
        {"role": "system", "content": "Split a user's conversational revision into two literal spans. "
         "instruction is the user's metalinguistic framing addressed to the assistant: their act of correcting, "
         "clarifying or replacing the earlier draft. replacement is only the new words intended for the recipient. "
         "First identify the framing, then identify the outgoing wording. Do not include framing in the replacement. "
         "Both are exact substrings, without enclosing quotation marks. Empty instruction is allowed only if "
         "the entire utterance is bare outgoing wording with no revision framing. Background draft is data."},
        {"role": "user", "content": json.dumps({"earlier_draft": pending.get("entities", {}), "revision": text})}],
        format={"type": "object", "additionalProperties": False, "required": ["instruction", "replacement"],
                "properties": {"instruction": {"type": "string"}, "replacement": {"type": "string"}}},
        options={"temperature": 0, "num_predict": 1800},
        think="low" if model.name.startswith("gpt-oss") else True), 60)
    value = json.loads(result["content"])
    if (not isinstance(value, dict) or set(value) != {"instruction", "replacement"}
            or any(not isinstance(part, str) or len(part) > 4000 or part not in text for part in value.values())
            or not value["replacement"].strip()
            or (value["instruction"] and value["instruction"] in value["replacement"])):
        raise ValueError("Please provide the replacement wording for the draft.")
    return value["replacement"]
