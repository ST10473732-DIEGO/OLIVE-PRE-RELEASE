"""Live local semantic routing only: no proposed application action is executed."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse

CASES = [
    ("What is recursion?", {}, "conversation.answer"),
    ("Explain Btrfs.", {}, "conversation.answer"),
    ("How does Proton work?", {}, "conversation.answer"),
    ("Why is my code failing?", {}, "conversation.answer"),
    ("Summarise this text: a recursive function calls itself.", {}, "conversation.answer"),
    ("Give me Python code for a calculator.", {}, "conversation.answer"),
    ("How would I make a calculator in C#?", {}, "conversation.answer"),
    ("Write the code for a calculator.", {}, "conversation.answer"),
    ("Show me an example.", {}, "conversation.answer"),
    ("Now add multiplication.", {"workspace_id": "fixture", "entities": {"project": "Calculator"}}, "code.modify"),
    ("Write a Python function that validates an email address.", {}, "conversation.answer"),
    ("How would I add a Save button?", {}, "conversation.answer"),
    ("Add that Save button to the selected project.", {"workspace_id": "fixture"}, "code.modify"),
    ("Show me how to open an application from Python.", {}, "conversation.answer"),
    ("Open my browser.", {}, "application.launch"),
    ("Explain this instruction: run the script.", {}, "conversation.answer"),
    ("Why does Python raise TypeError when I add a string and a number?", {}, "conversation.answer"),
    ("Show that previous code in JavaScript.", {}, "conversation.answer"),
    ("Stop the current task.", {"active_task": {"state": "running"}}, "task.cancel"),
    ("Run the selected project.", {"workspace_id": "fixture"}, "code.run"),
]

async def main():
    with tempfile.TemporaryDirectory(prefix="olive-routing-") as root:
        async def deny(request): return ConfirmationResponse(False)
        s = ServiceContainer(lambda *a: None, deny, Path(root), migrate=False)
        results = []
        try:
            await s.model_registry.refresh()
            for text, context, expected in CASES:
                result = await s.interaction.interpreter.interpret(text, context)
                actual = [step["intent"] for step in result["steps"]]
                record = {"request": text, "expected": expected, "actual": actual,
                          "passed": actual == [expected], "clarification": result["clarification"]}
                results.append(record)
                print(json.dumps(record), flush=True)
            Path(sys.argv[1]).write_text(json.dumps(results, indent=2), encoding="utf-8")
            if not all(r["passed"] for r in results): raise SystemExit(1)
        finally:
            await s.shutdown()

if __name__ == "__main__": asyncio.run(main())
