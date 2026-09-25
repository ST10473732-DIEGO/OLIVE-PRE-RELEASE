"""Provider-neutral, bounded semantic interpretations. No executable model prose."""

import json
import math
from datetime import date


INTENTS = (
    "conversation.answer", "application.launch", "application.activate", "application.navigate",
    "application.search", "application.control", "communication.compose",
    "communication.send", "communication.attach", "media.search", "media.play", "media.pause", "media.next", "media.previous",
    "browser.navigate", "browser.search", "browser.interact",
    "filesystem.search", "filesystem.open", "filesystem.move", "filesystem.copy", "filesystem.trash", "filesystem.create_file", "filesystem.edit_file",
    "filesystem.create_directory", "filesystem.list", "code.inspect",
    "code.modify", "code.run", "code.test", "research.start", "research.follow_up",
    "project.open", "project.create", "project.add_file", "knowledge.query", "memory.query", "task.cancel", "task.pause",
    "task.resume", "task.correct", "task.repeat",
)
SLOTS = (
    "application", "server", "channel", "recipient", "message", "subject", "query",
    "url", "path", "destination", "project", "target", "expected", "action", "date", "text",
    "date_until", "time_basis", "order", "settings_page", "previous_application", "sender_mode",
    "topic", "extension", "time_until", "language", "attachment_id",
)
ACTIONS = ("set_text", "invoke", "select", "search", "expand", "collapse", "scroll", "focus", "fill", "click", "new_tab")
INTENT_SLOTS = {
    "knowledge.query": {"path", "query", "attachment_id"},
    "filesystem.search": {"query", "path", "date", "date_until", "time_basis", "order", "topic", "extension", "time_until"},
    "filesystem.open": {"path"}, "filesystem.move": {"path", "destination"},
    "filesystem.copy": {"path", "destination"},
    "filesystem.trash": {"path"},
    "filesystem.create_file": {"path","text"}, "filesystem.edit_file": {"path","text"},
    "filesystem.create_directory": {"path"}, "filesystem.list": {"path"},
    "project.open": {"project"},
    "project.create": {"project", "language", "query"},
    "code.run": set(),
    "code.test": {"query"},
    "code.modify": {"query", "path", "project"},
    "project.add_file": {"project", "path"},
    "application.launch": {"application"},
    "application.activate": {"application"},
    "browser.navigate": {"application", "url"},
    "browser.search": {"application", "query", "target"},
    "browser.interact": {"application", "target", "text", "action", "expected"},
    "application.search": {"application", "query", "target"},
    "application.navigate": {"application", "target", "server", "channel", "url", "settings_page"},
    "application.control": {"application", "target", "text", "action", "expected"},
    "communication.compose": {"application", "recipient", "server", "channel", "message", "subject", "path", "sender_mode"},
    "communication.send": {"application", "recipient", "server", "channel", "message", "subject", "path", "sender_mode"},
    "communication.attach": {"application", "path", "target"},
    "media.play": {"application", "query"}, "media.pause": {"application"},
    "media.search": {"application", "query"},
    "media.next": {"application"}, "media.previous": {"application"},
    "research.start": {"query", "project", "path"}, "research.follow_up": {"query", "project"},
    "task.cancel": set(), "task.pause": set(), "task.resume": set(), "task.repeat": set(),
}
from ..personal.language import INTENTS as PERSONAL_INTENTS, SLOTS as PERSONAL_SLOTS, SLOT_MAP
from ..mail.language import INTENTS as MAIL_INTENTS,SLOTS as MAIL_SLOTS,SLOT_MAP as MAIL_SLOT_MAP
INTENTS += MAIL_INTENTS
SLOTS += tuple(sorted(MAIL_SLOTS-set(SLOTS)))
INTENT_SLOTS.update(MAIL_SLOT_MAP)
INTENTS += PERSONAL_INTENTS
SLOTS += tuple(sorted(PERSONAL_SLOTS-set(SLOTS)))
for _intent in PERSONAL_INTENTS:
    INTENT_SLOTS[_intent]=SLOT_MAP[_intent]


def entity_schema(key):
    value={"type":"string"}
    if key=='language':value.update(enum=['python','csharp','javascript','java','unsupported'],description='Canonical programming language identifier, never explanation. Omit if unspecified (defaults to Python). If the user requests another language, use unsupported and explain in clarification; never substitute a supported language.')
    if key=='sender_mode':value.update(enum=['bot','personal'],description='Preserve explicit requested sender identity: personal for a normal/user account, bot for an application bot. Omit when unspecified.')
    if key in {'record_id','person_id','event_id','personal_task_id','calendar_id','proposal_id','reminder_id'}:value['pattern']=r'^[0-9a-f]{32}$'
    if key=='delivery_id':value['pattern']=r'^[0-9a-f]{64}$'
    if key in {'duration_minutes','offset_minutes','minutes'}:value['pattern']=r'^[0-9]+$'
    if key=='shift_minutes':value['pattern']=r'^-?[0-9]+$'
    if key=='all_day':value['enum']=['true','false']
    if key=='priority':value.update(enum=['low','normal','high'],description='Task priority only when requested; omit for the normal default.')
    if key=='recurrence':value.update(pattern=r'^(FREQ=(DAILY|WEEKLY|MONTHLY|YEARLY)(;.*)?)?$',description='Omit for a one-time event. Otherwise a standard RRULE beginning FREQ=. Never true/false.')
    if key=='folder':value['description']='An explicitly requested actual Mail folder/label such as Inbox or Trash. Omit for local/cached/all mail: those describe scope, not a folder.'
    return value


def schema(known_references=None, intents=INTENTS, max_steps=12):
    references = SLOTS if known_references is None else [key for key in SLOTS if key in known_references]
    entities = {key: entity_schema(key) for key in SLOTS}
    for key in ("server", "channel", "project", "application"):
        entities[key]["description"] = f"The exact {key} name, separate from words describing its kind. Preserve words that are explicitly part of the name."
    entities["target"]["description"] = "Other UI destination/control name. Use the server/channel/project slots for those named entities."
    entities["message"]["description"] = "Literal communication body/content/wording supplied by the user, separate from the subject and destination. Preserve the complete body."
    entities["subject"]["description"] = "Literal email subject line, separate from its message body."
    entities["action"] = {"type": "string", "enum": list(ACTIONS)}
    entities["settings_page"] = {"enum": ["bluetooth", "display", "network", "apps"]}
    entities["date"] = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$",
                        "description": "ISO local date, only when the user requests a date filter."}
    entities["query"]["description"] = "For file search: filename glob, e.g. report.pdf or *.pdf. For research/code: the user's objective."
    variants = []
    for intent in intents:
        if intent.startswith(("profile.", "contacts.")):
            continue  # Retain legacy decoding/storage, remove public capability proposals.
        slots = INTENT_SLOTS.get(intent, set(SLOTS))
        slots = slots - {'person_id'}  # Historical links remain stored; Contacts is not a public feature.
        # Native records have their own selected identities. Scalar attributes
        # (title/time/duration) are interpreted into entities, not unresolved
        # aliases of the last unrelated record's scalar fields.
        reference_slots=slots if intent not in PERSONAL_INTENTS else {key for key in slots if key.endswith('_id') or key=='project'}
        step = {"intent": {"const": intent},
                "entities": {"type": "object", "additionalProperties": False,
                             "properties": {key: value for key, value in entities.items() if key in slots}},
                "references": {"type": "object", "additionalProperties": False,
                               "description": "Only omitted values explicitly reused from context. Never include a key present in entities. Usually empty when the user supplies new content. A new record's title must not also refer to an earlier record's title.",
                               "properties": {key: ({"enum": ["path", "other_path"]} if key == "path" else {"const": key})
                                              for key in references if key in reference_slots}}}
        if intent == "filesystem.search":
            step["entities"]["required"] = ["query"]
        if intent=='calendar.create':
            step['entities']['required']=['title','start']
        if intent=='calendar.free_busy':
            step['intent']['description']='Find free/unbooked time slots or gaps for a requested duration. This answers availability questions, not calendar.search.'
        if intent=='calendar.search':
            step['intent']['description']='List existing booked events. Cannot answer requests for free time, available blocks or scheduling gaps; use calendar.free_busy for those.'
        if "application" in slots and known_references and "previous_application" in known_references:
            step["references"]["properties"]["application"] = {"enum": ["application", "previous_application"]}
        variants.append({"type": "object", "additionalProperties": False,
                         "required": list(step), "properties": step})
    fields = {"confidence": {"type": "number", "minimum": 0, "maximum": 1},
              "clarification": {"type": "string"},
              "steps": {"type": "array", "minItems": 1, "maxItems": max_steps,
                        "items": {"anyOf": variants}}}
    return {"type": "object", "additionalProperties": False,
            "required": list(fields), "properties": fields}


def parse(raw,known_context=None):
    if not isinstance(raw, str) or len(raw) > 24000:
        raise ValueError("The interpretation exceeded its size limit")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate interpretation field")
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(value, dict) or set(value) != {"confidence", "clarification", "steps"}:
        raise ValueError("Invalid interpretation schema")
    confidence = value["confidence"]
    if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError("Invalid interpretation confidence")
    if not isinstance(value["clarification"], str) or len(value["clarification"]) > 500:
        raise ValueError("Invalid clarification")
    if not isinstance(value["steps"], list) or not 1 <= len(value["steps"]) <= 12:
        raise ValueError("Invalid intent sequence")
    for step in value["steps"]:
        if not isinstance(step, dict) or set(step) != {"intent", "entities", "references"}:
            raise ValueError("Invalid intent step")
        if step["intent"] not in INTENTS:
            raise ValueError("Unsupported intent")
        for group in ("entities", "references"):
            entries = step[group]
            if not isinstance(entries, dict) or set(entries) - set(SLOTS):
                raise ValueError("Unknown entity field")
            if any(not isinstance(v, str) or len(v) > 4000 for v in entries.values()):
                raise ValueError("Invalid entity value")
        if step['intent'] == 'project.create' and step['entities'].get('language'):
            language = step['entities']['language'].strip().lower()
            language = {'c#': 'csharp', 'cs': 'csharp', 'js': 'javascript', 'py': 'python'}.get(language, language)
            if language not in {'python', 'csharp', 'javascript', 'java', 'unsupported'}:
                raise ValueError('Use a canonical programming language identifier without commentary, or unsupported with clarification. Omit an unspecified language.')
            step['entities']['language'] = language
        if step['intent'] in PERSONAL_INTENTS:
            specific={'contacts':'person_id','calendar':'event_id','tasks':'personal_task_id','reminders':'reminder_id'}.get(step['intent'].split('.')[0])
            generic=step['entities'].get('record_id')
            if specific and generic and step['entities'].get(specific) and generic!=step['entities'][specific]:
                raise ValueError('Conflicting target ID aliases. Use one actual record ID; put a supplied name in query, never record_id.')
        overlap=set(step["entities"]) & set(step["references"])
        for key in overlap:
            reference=step['references'][key]
            # A native record ID can be expressed literally and redundantly as
            # the SAME already-resolved context ID. Canonicalise only that exact
            # equivalence; conflicting or unknown references remain rejected.
            if (step['intent'] in PERSONAL_INTENTS and key.endswith('_id') and reference==key
                    and known_context and known_context.get(key)
                    and step['entities'][key]==known_context[key]):
                del step['references'][key]
            else:raise ValueError('An entity cannot also be an unresolved reference: '+key+'. Choose one source: keep the explicitly requested literal in entities and OMIT references.'+key+'; use references only if that value was omitted and the user requests reusing context. Do not change the requested operation.')
        if "action" in step["entities"] and step["entities"]["action"] not in ACTIONS:
            raise ValueError("Unsupported semantic action")
        if 'recurrence' in step['entities']:
            from ..personal.calendar import validate_rule
            from datetime import datetime,timezone
            rule=step['entities']['recurrence']
            # Validate grammar here; the native service validates real dates and
            # profile timezone. UTC UNTIL needs an aware parser anchor.
            anchor=datetime(2000,1,1,tzinfo=timezone.utc) if any(part.startswith('UNTIL=') and part.endswith('Z') for part in rule.upper().split(';')) else None
            validate_rule(rule,anchor)
        if 'priority' in step['entities'] and step['entities']['priority'] not in {'low','normal','high'}:
            raise ValueError('Task priority must be low, normal or high; omit when unspecified')
        if "url" in step["entities"]:
            from urllib.parse import urlsplit
            url = step["entities"]["url"]
            parsed_url = urlsplit(url)
            if (parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname
                    or parsed_url.username is not None or parsed_url.password is not None
                    or any(ch.isspace() for ch in url)):
                raise ValueError("Navigation requires an HTTP(S) website without credentials. Returning to an existing application is application.activate, not URL navigation.")
        if (step["intent"] == "application.control" and step["entities"].get("action") in {"set_text", "fill"}
                and (not step["entities"].get("text") or not step["entities"].get("target"))):
            raise ValueError("Text entry requires actual user-requested text and a field; reconsider whether this is a different operation")
        if step["intent"] == "filesystem.search" and not step["entities"].get("query", "").strip():
            raise ValueError("File search requires a filename query")
        if step['intent']=='calendar.create' and not value['clarification'] and (not step['entities'].get('title') or not step['entities'].get('start')):
            raise ValueError('Keep all supplied event attributes in one calendar.create step, including title, start and requested duration/end; do not split attributes into update operations. Clarify a missing date/time.')
        if step["intent"] in {"application.search", "browser.search", "media.search"} and not step["entities"].get("query", "").strip():
            raise ValueError("Search terms belong in query; preserve what the user wants to find")
        if step["entities"].get("date"):
            value_date = step["entities"]["date"]
            if date.fromisoformat(value_date).isoformat() != value_date:
                raise ValueError("Date filters must use ISO local dates")
        if step["intent"] in INTENT_SLOTS and (set(step["entities"]) | set(step["references"])) - INTENT_SLOTS[step["intent"]]:
            raise ValueError("Invalid slots for " + step["intent"] + "; allowed: " + ", ".join(sorted(INTENT_SLOTS[step["intent"]])))
        if any(key != value and (key, value) not in {("path", "other_path"), ("application", "previous_application")} for key, value in step["references"].items()):
            raise ValueError("References must name the same context slot")
    native_creations=[json.dumps(step,sort_keys=True) for step in value['steps'] if step['intent'] in PERSONAL_INTENTS and step['intent'].endswith('.create')]
    if len(native_creations)!=len(set(native_creations)):raise ValueError('Duplicate native creation intent. A single requested record needs one creation step; clarify if separate identical records were intended.')
    return value
