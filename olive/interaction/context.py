"""Bounded session context; observations cannot become commands or permissions."""

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


def normalize_pending_intent(value, context):
    """Composing into the one unsent draft is a revision, never implicit submission."""
    pending = context.get("pending_draft")
    if (pending and pending.get("type") == "communication" and pending.get("state") != "sent"
            and len(value["steps"]) == 1 and value["steps"][0]["intent"] == "communication.compose"):
        value = deepcopy(value)
        value["steps"][0]["intent"] = "task.correct"
    return value


@dataclass
class InteractionContext:
    entities: dict = field(default_factory=dict)
    recent: list = field(default_factory=list)
    pending: dict | None = None
    personal_pending: dict = field(default_factory=dict)
    last_steps: list = field(default_factory=list)
    project_id: str | None = None
    workspace_id: str | None = None
    clarification: dict | None = None
    file_candidates: list = field(default_factory=list)
    studio_selection: tuple | None = None
    tab_id: str | None = None
    browser_application: str | None = None
    application_contexts: dict = field(default_factory=dict)
    research_session_id: str | None = None
    research_depth: str | None = None
    editor_context: dict | None = None
    media_application: str | None = None
    chat_id: str | None = None
    last_interpretation: dict = field(default_factory=dict)
    resolved_steps: list = field(default_factory=list)
    last_outcome: dict | None = None  # Verified typed outcome of the previous step in this task only.
    message_id: str | None = None  # The user turn the current request belongs to (task cards anchor to it).
    coding_follow_up: bool = False  # This request continues the conversation's own recent coding task.

    def snapshot(self):
        return deepcopy({"entities": self.entities, "recent_user_turns": self.recent[-6:],
                         "repeatable_task": bool(self.last_steps) and not any(step['intent'] in {'personal.commit','personal.correct','personal.cancel','mail.send','mail.save_proposal'} for step in self.last_steps),
                         "pending_draft": self.pending, "project_id": self.project_id,
                         "native_proposals": [{"id":p['id'],"revision":p['revision'],"operation":p['method'],"fields":{k:x for k,x in p['body'].items() if k in {'title','display_name','start','end','due','timezone'}}} for p in self.personal_pending.values()],
                         "workspace_id": self.workspace_id, "clarification": self.clarification,
                         "untrusted_editor_context": self.editor_context,
                         "untrusted_file_result_metadata": self.file_candidates[:30],
                         "recent_applications": list(self.application_contexts)[-6:],
                         "browser_application": self.browser_application,
                         "research_session_id": self.research_session_id,
                         "media_application": self.media_application,
                         "local_date": datetime.now().date().isoformat()})

    def remember_user(self, text):
        self.recent.append(text[:2000])
        self.recent[:] = self.recent[-6:]

    def resolve(self, step):
        result = deepcopy(step)
        for slot, reference in step["references"].items():
            # The interpreter must name an exact known context slot, not guess a value.
            available = dict(self.entities)
            if self.pending and self.pending.get("state") != "sent":
                available.update(self.pending.get("entities", {}))
            if slot == "path" and reference == "other_path":
                others = [path for path in self.file_candidates if path != self.entities.get("path")]
                if len(others) != 1 or self.entities.get("path") not in self.file_candidates:
                    raise ValueError("Which other file do you mean?")
                result["entities"]["path"] = others[0]
                continue
            if slot == "application" and reference == "previous_application":
                if not available.get(reference):
                    raise ValueError("Which previous application do you mean?")
                result["entities"][slot] = available[reference]
                continue
            if reference not in available or reference != slot:
                raise ValueError(f"Which {slot.replace('_', ' ')} do you mean?")
            result["entities"][slot] = available[reference]
        result["references"] = {}
        path = result["entities"].get("path")
        if path and not Path(path).is_absolute():
            matches = [candidate for candidate in self.file_candidates if Path(candidate).name.casefold() == path.casefold()]
            if len(matches) > 1:
                raise ValueError("Several files have that name. Which location should I use?")
            if matches:
                result["entities"]["path"] = matches[0]
        return result

    def accept(self, step):
        # Only resolved user-command entities enter this state. Never raw tool output.
        application = step["entities"].get("application")
        current = self.entities.get("application")
        if application and current and application.casefold() != current.casefold():
            scoped = ("server", "channel", "url", "target")
            self.application_contexts[current.casefold()] = {key: self.entities[key] for key in scoped if key in self.entities}
            self.entities["previous_application"] = current
            for key in scoped:
                self.entities.pop(key, None)
            self.entities.update(self.application_contexts.get(application.casefold(), {}))
            while len(self.application_contexts) > 6:
                self.application_contexts.pop(next(iter(self.application_contexts)))
        for key, value in step["entities"].items():
            if key == "path" and step["intent"] == "filesystem.search":
                continue  # Keep the selected result, not the search directory, as 'the file'.
            self.entities[key] = value[:4000]
