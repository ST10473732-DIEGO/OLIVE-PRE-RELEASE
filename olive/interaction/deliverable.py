"""Conservative, non-authorizing fast path for explicit conversational output.

Unrecognized requests still use semantic interpretation. These rules can only
remove tools; they never authorize an action or infer a workspace from context.
"""

import re
from enum import StrEnum


class Deliverable(StrEnum):
    ANSWER = "answer"
    EXPLANATION = "explanation"
    CODE = "code"
    DRAFT = "draft"
    DOCUMENT_ANALYSIS = "document_analysis"
    WEB_ANSWER = "web_backed_answer"
    CREATION = "file_project_creation"
    EXECUTION = "execution"
    COMMUNICATION = "external_communication"
    CORRECTION = "correction_cancellation"


def direct_deliverable(text, context):
    """Recognize clear output requests, deferring mixed/contextual work.

    Quoted payloads are never inspected for authorization. Requests containing
    multiple clauses defer to the semantic gate, whose answer boundary remains
    read-only. A selected source must keep its authorized retrieval path.
    """
    value = text.strip().lower()
    value = re.sub(r"^(?:please\s+|(?:can|could|would) you\s+)", "", value)
    value = re.sub(r"^please\s+", "", value)
    if context.get("entities", {}).get("path"):
        return None
    if re.search(r"\b(?:selected|attached|existing|my) (?:source|code|file|document|project|workspace|script|function|handler)\b", value):
        return None
    if re.search(r"\b(?:and then|then|also)\b|[;\n]", value):
        return None
    if re.search(r"[.!?]\s+\S", value):
        return None
    if re.search(r"\b(?:and|,)[ ]*(?:save|run|execute|send|create|open|write|build)\b", value):
        return None
    if re.match(r"(?:explain (?:how\b|this (?:instruction|quotation)\b)|how (?:do|can|would|should)\b)", value):
        return Deliverable.EXPLANATION
    if re.search(r"\b(?:in|into|to) (?:the |my )?(?:studio|workspace|project|file)\b", value):
        return None
    if re.match(r"(?:give|show) me (?:the |a |an |some )?(?:\w+ )?(?:code|script|example)\b", value):
        return Deliverable.CODE
    if re.match(r"(?:write|generate|provide) (?:me )?(?:a |an |some )?(?:(?:simple|sample|example|python|c#|javascript) )?(?:code|script|function)\b", value):
        return Deliverable.CODE
    if not (context.get("pending_draft") or context.get("native_proposals") or context.get("entities", {}).get("draft_id")):
        if re.match(r"(?:write|draft) (?:me )?(?:an? )?(?:email|message|letter) (?:saying|that says|about)\b", value):
            return Deliverable.DRAFT
    return None
