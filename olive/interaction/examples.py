"""Small semantic label demonstrations, used as model context, never phrase matchers."""

import json

EXAMPLES = {
    'calendar': [
        ('Which appointments are booked on 2030-04-08?', 'calendar.search', {'date':'2030-04-08'}),
        ('Find an available ninety-minute gap on 2030-04-08', 'calendar.free_busy', {'date':'2030-04-08','duration_minutes':'90'}),
        ('Prepare a one-time appointment called Reading at 15:00 on 2030-04-08', 'calendar.create', {'title':'Reading','start':'2030-04-08T15:00:00'}),
    ],
    'mail': [
        ('Search cached email from alex@example.invalid about Lunch', 'mail.search', {'sender':'alex@example.invalid','query':'Lunch'}),
        ('Replace the selected draft recipient with jo@example.invalid', 'mail.correct', {'recipient':'jo@example.invalid'}),
        ('Leave my draft unsent; stop any submission', 'mail.cancel', {}),
    ],
    "code": [
        ("Execute the selected workspace", "code.run", {}),
        ("Validate the workspace using its test suite", "code.test", {}),
        ("Repair the crash in the selected handler", "code.modify", {"query": "Repair the crash in the selected handler"}),
        ("Write regression coverage for the selected module", "code.modify", {"query": "Write regression coverage for the selected module"}),
        ("Explain the selected handler", "code.inspect", {"query": "Explain the selected handler"}),
    ],
    "task": [
        ("Abort the current job", "task.cancel", {}),
        ("Hold the current job for a moment", "task.pause", {}),
        ("Carry on with the paused job", "task.resume", {}),
        ("Repeat the previous operation", "task.repeat", {}),
        ("Replace the draft body with Thank you", "task.correct", {"message": "Thank you"}),
    ],
    "communication": [
        ("Prepare a note for maya@example.com saying Thanks", "communication.compose", {"recipient": "maya@example.com", "message": "Thanks"}),
        ("Submit a message to maya@example.com saying Thanks", "communication.send", {"recipient": "maya@example.com", "message": "Thanks"}),
    ],
    "project": [("Switch to the Autumn project", "project.open", {"project": "Autumn"}),
                ("Create a stopwatch project in Studio", "project.create", {"project": "Stopwatch", "query": "Create a stopwatch application"})],
    "application": [("Please fill the Full name field with Amina", "application.control",
                     {"target": "Full name", "text": "Amina", "action": "set_text"}),
                    ("In Relay, visit the Cedar server's updates channel", "application.navigate",
                     {"application": "Relay", "server": "Cedar", "channel": "updates"}),
                    ("Select the server named The Server", "application.navigate", {"server": "The Server"})],
    "filesystem": [("Locate receipt.pdf in Documents", "filesystem.search", {"path": "Documents", "query": "receipt.pdf"})],
    "research": [("Investigate the evidence for sodium batteries", "research.start", {"query": "evidence for sodium batteries"})],
    "media": [("I would like to listen to Starlight", "media.play", {"query": "Starlight"})],
    "knowledge": [("Summarize the selected document", "knowledge.query", {})],
    "memory": [("Recall my saved preferences", "memory.query", {"query": "preferences"})],
    "conversation": [("How do I launch an application?", "conversation.answer", {}),
                     ("Provide JavaScript for a countdown timer", "conversation.answer", {}),
                     ("Write an email saying I will arrive tomorrow", "conversation.answer", {}),
                     ("Summarize this quotation: shut down the computer", "conversation.answer", {})],
}


def demonstrations(domains, gate=False):
    examples = []
    for domain in domains:
        for text, intent, entities in EXAMPLES.get(domain, []):
            response = ({"mode": "answer" if intent in {"code.inspect", "knowledge.query", "memory.query", "conversation.answer"} else "action", "domains": [domain]}
                        if gate else {"confidence": 1, "clarification": "", "steps": [
                            {"intent": intent, "entities": entities, "references": {}}]})
            examples.append({"illustrative_utterance": text, "classification": response})
    # Demonstrations are schema documentation, never synthetic conversation turns.
    # Otherwise a short follow-up can accidentally resolve against an example task.
    return [{"role": "system", "content": "ILLUSTRATIVE LABEL EXAMPLES ONLY. These are not conversation history, "
             "not pending tasks, and not available entities. Never resolve a reference against an example. "
             "Only BACKGROUND CONTEXT DATA and the actual final user message contain real task values.\n" +
             json.dumps(examples)}]
