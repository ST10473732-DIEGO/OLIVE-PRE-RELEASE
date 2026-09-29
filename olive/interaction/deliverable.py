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


def instruction_text(text):
    """Ignore supplied code/quoted payloads when considering execution authority."""
    text = re.sub(r'```[^\n]*\n.*?(?:```|$)', ' [supplied code] ', text, flags=re.S)
    return re.sub(r'([\'"])(?:(?!\1).)*?\1', ' [quoted content] ', text, flags=re.S).strip().lower()


def code_action_requested(text, context=None):
    """Require a current explicit software target or execution request.

    Being inside Studio, model classification, or action words in pasted source
    do not authorize effects. This guard can only remove authority.
    """
    value = instruction_text(text)
    # Negative effect clauses are constraints, never positive execution requests.
    value = re.sub(r"\b(?:do not|don't|never)\s+[^.;\n]+", '', value)
    if re.search(r'\b(?:in|into|to) (?:the |my )?(?:studio|workspace|project|file)\b', value):
        return True
    if re.search(r'\b(?:selected|current|existing|my) (?:file|project|workspace|repository)\b', value):
        return True
    if re.search(r'\b(?:this|my) (?:project|workspace|repository|repo|codebase|api)\b', value):
        return True
    if re.search(r'\b(?:create|open)\b.*\bproject (?:named|called)\b', value):
        return True
    if re.search(r'(?:^|\bthen\s+|\band\s+|[.;]\s*)(?:run|execute|compile|build|save|apply)\b(?! instructions?\b)', value):
        # "Build me an app" without a filesystem or execution destination is
        # source generation, not authority to create a workspace.
        return not bool(re.match(r'build (?:me )?(?:an? )?(?:\w+[ #+.-]*)?app\b', value))
    return False


def direct_deliverable(text, context):
    """Recognize clear output requests, deferring mixed/contextual work.

    Quoted payloads are never inspected for authorization. Requests containing
    multiple clauses defer to the semantic gate, whose answer boundary remains
    read-only. A selected source must keep its authorized retrieval path.
    """
    value = instruction_text(text)
    value = re.sub(r"^(?:please\s+|(?:can|could|would) you\s+)", "", value)
    value = re.sub(r"^please\s+", "", value)
    if context.get("entities", {}).get("path") and '[supplied code]' not in value and re.search(
            r'\b(?:this|that|selected|attached|existing|my) (?:source|code|file|document|project|workspace|script|function|handler)\b', value):
        return None
    if re.search(r"\b(?:selected|attached|existing|my) (?:source|code|file|document|project|workspace|script|function|handler)\b", value):
        return None
    if code_action_requested(text, context):
        return None
    if re.search(r"[.!?;]\s*(?:open|launch|send|delete|create|run|execute)\b", value):
        return None
    if re.match(r"(?:explain (?:how\b|this (?:instruction|quotation)\b)|how (?:do|can|would|should)\b)", value):
        return Deliverable.EXPLANATION
    if re.search(r"\b(?:in|into|to) (?:the |my )?(?:studio|workspace|project|file)\b", value):
        return None
    if re.match(r"(?:explain|suggest a patch|show (?:me )?a patch)\b", value) and not re.search(r'\b(?:my latest|selected|attached)\b', value):
        return Deliverable.EXPLANATION
    # Language names are free text. No compiler/template allowlist governs Chat.
    software = r'\b(?:code|script|function|class|method|component|app|application|program|website|web page|login screen|http server|query|regex|unit tests?|patch|implementation)\b'
    if re.match(r"(?:give|show|provide)\b", value) and re.search(software, value):
        return Deliverable.CODE
    if re.match(r"(?:write|generate|implement|make|build|design|create)\b", value) and re.search(software, value) and not re.search(r'\b(?:reminder|calendar|email|message|task)\b', value.split('[supplied code]')[0]):
        return Deliverable.CODE
    if not (context.get("pending_draft") or context.get("native_proposals") or context.get("entities", {}).get("draft_id")):
        if re.match(r"(?:write|draft) (?:me )?(?:an? )?(?:email|message|letter) (?:saying|that says|about)\b", value):
            return Deliverable.DRAFT
    return None
