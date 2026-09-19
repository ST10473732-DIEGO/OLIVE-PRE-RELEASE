"""Opt-in visible desktop smoke exercise using temporary data and workspace only.

Run with --live-model to exercise an installed Ollama model. No model downloads.
Screenshots and a redacted result summary are written to the supplied output folder.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile
import json
import subprocess
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
parser = argparse.ArgumentParser()
parser.add_argument("--live-model", action="store_true")
parser.add_argument("--output", default=".qt-smoke")
args = parser.parse_args()
output = Path(args.output).resolve()
output.mkdir(parents=True, exist_ok=True)
temporary = tempfile.TemporaryDirectory(prefix="olive-qt-smoke-")
root = Path(temporary.name)
os.environ["OLIVE_DATA_DIR"] = str(root / "data")
from PySide6.QtCore import QTimer
from olive.application.service_container import ServiceContainer
from olive.ui_qt.application import OliveApplication
from olive.services.ollama_service import ModelInfo
from types import SimpleNamespace
import asyncio

workspace = root / "workspace"
workspace.mkdir()
(workspace / "tests").mkdir()
(workspace / "main.py").write_text(
    """from http.server import HTTPServer, BaseHTTPRequestHandler
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><title>OLIVE Preview Test</title><h1>OLIVE local preview</h1></html>")
server=HTTPServer(("127.0.0.1", 0), Handler)
print(f"http://127.0.0.1:{server.server_port}", flush=True)
print("main.py:2:1: warning: Fixture warning", flush=True)
server.serve_forever()
""",
    encoding="utf-8",
)
(workspace / "tests" / "test_example.py").write_text(
    "import unittest\nclass Example(unittest.TestCase):\n    def test_add(self): self.assertEqual(1+1,2)\n",
    encoding="utf-8",
)
for command in (
    ["git", "init"],
    ["git", "add", "."],
    ["git", "-c", "user.name=OLIVE Smoke", "-c", "user.email=smoke@localhost", "commit", "-m", "Fixture"],
):
    subprocess.run(
        command,
        cwd=workspace,
        capture_output=True,
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


class SmokeServices(ServiceContainer):
    async def initialize(self):
        if args.live_model:
            await super().initialize()
        else:
            self.model_infos = [ModelInfo("fixture")]
            self.ollama_state = "Smoke fixture"
            self.chats[self.current_chat_id].model = "fixture"

            async def reply(*args, **kwargs):
                async def tokens():
                    for token in ["OLIVE ", "desktop ", "streaming ", "works."]:
                        await asyncio.sleep(0.2)
                        yield token

                return tokens(), SimpleNamespace(rag_results=[], memories=[])

            self.chat_service.stream_reply = reply
            async def interpret(text, context):
                # This smoke verifies Qt/runtime transport, not model understanding.
                # Installed-model language evaluation runs separately.
                return {"confidence": 1, "clarification": "", "steps": [
                    {"intent": "conversation.answer", "entities": {}, "references": {}}]}
            self.interaction.interpreter.interpret = interpret
            self.publish("models", self.data.models())
            self.publish("status", self.data.status())


def factory(emit, confirm):
    return SmokeServices(emit, confirm, root / "data", migrate=False)


application = OliveApplication(factory=factory, presentation="legacy")
app = application.qt
manager = application.manager
bridge = application.bridge
results = {
    "startup_ms": application.startup_ms,
    "mode": "live Ollama" if args.live_model else "deterministic stream fixture",
    "checks": {},
    "errors": [],
}
state = {"stage": 0, "started": time.monotonic(), "stream_events": 0, "shutdown": False}


def unhandled_callback(kind, value, traceback):
    results["errors"].append("Unhandled Qt callback: " + kind.__name__)
    sys.__excepthook__(kind, value, traceback)


sys.excepthook = unhandled_callback


def record(name, ok=True):
    results["checks"][name] = bool(ok)
    print(name, "PASS" if ok else "FAIL", flush=True)


def result_callback(name, after=None):
    def callback(value, error):
        if error:
            results["errors"].append(name + ": " + error)
            record(name, False)
        else:
            record(name)
        if after:
            after(value)

    return callback


def confirmation(request):
    # Only this explicit temporary-fixture smoke runtime auto-clicks confirmations.
    # Production ConfirmationService and permission defaults are unchanged.
    dialog = manager.dialogs.get(request.id)
    if dialog:
        QTimer.singleShot(100, dialog.approve)
        record("confirmation presentation")


bridge.confirmation.connect(confirmation)


def initialize():
    record("Home is initial workspace", manager.navigation.current == "home")
    for feature in manager.registry.list():
        manager.open(feature.id)
        record(feature.title + " opens")
    home = manager.open("home")
    record("features share one primary window", all(not page.isWindow() and page.window() is manager.main for page in manager.pages.values()))
    from PySide6.QtWidgets import QPushButton
    next(button for button in home.findChildren(QPushButton) if button.text() == "Open Chat").click()
    record("Home card navigates main workspace", manager.main.stack.currentWidget() is manager.pages["chat"])
    manager.navigation.back()
    record("workspace history returns Home", manager.navigation.current == "home")
    def capture_home():
        manager.main.grab().save(str(output / "home.png"))
        bridge.call("data.create_workspace", workspace_ready, title="Desktop smoke", path=str(workspace))
    QTimer.singleShot(400, capture_home)


def workspace_ready(value, error):
    if error:
        results["errors"].append(error)
        finish()
        return
    state["workspace_id"] = value["id"]
    record("approved workspace persistence")
    studio = manager.open("studio")
    studio.workspace_id = value["id"]
    studio.load_tree()
    studio.open_file("main.py")
    state["stage"] = 1


def tick():
    if state["shutdown"]:
        return
    if time.monotonic() - state["started"] > 360:
        results["errors"].append("Smoke timeout")
        finish()
        return
    studio = manager.windows.get("studio")
    if state["stage"] == 1 and studio.tabs.count():
        record("file opens")
        editor = studio.tabs.currentWidget()
        editor.moveCursor(editor.textCursor().MoveOperation.End)
        editor.insertPlainText("\n# Native Qt edit smoke\n")
        studio.save()
        state["stage"] = 2
    elif state["stage"] == 2 and not studio.tabs.currentWidget().document().isModified():
        record("hash checked file save", "Native Qt edit smoke" in (workspace / "main.py").read_text())
        studio.run()
        state["stage"] = 3
    elif state["stage"] == 3 and getattr(studio, "local_url", None):
        record("Run and streaming output")
        studio.open_preview()
        state["stage"] = 4
        studio.preview.view.loadFinished.connect(preview_ready)
        studio.preview.page.loadingChanged.connect(lambda info: results.setdefault("preview_load_events", []).append(
            {"status": info.status().name, "error": info.errorString(), "code": info.errorCode()}))
    elif state["stage"] == 5 and studio.tests.rowCount():
        record("structured tests panel", studio.tests.item(0, 1).text() == "passed")
        if studio.problems.rowCount():
            studio.problems.selectRow(0)
            studio.open_problem()
            record("Problems navigation", studio.tabs.currentWidget().cursor_position()[0] == 2)
        else:
            record("Problems navigation", False)
        studio.grab().save(str(output / "studio.png"))
        bridge.call(
            "studio.git",
            result_callback("Git state", agent_start),
            workspace_id=state["workspace_id"],
            action="status",
        )
        state["stage"] = 6


def preview_ready(ok):
    if state["stage"] != 4:
        return
    record("localhost WebEngine preview", ok)
    studio = manager.windows["studio"]
    studio.preview.grab().save(str(output / "preview.png"))
    studio.preview.close()
    bridge.call(
        "studio.stop",
        result_callback("Run Stop", restart_run),
        session_id=studio.session_id,
    )
    state["stage"] = 45


def restart_run(value):
    bridge.call("studio.restart", restarted, workspace_id=state["workspace_id"])


def restarted(value, error):
    record("Run Restart", bool(value) and not error)
    if error:
        results["errors"].append(error)
        finish()
        return

    def stopped(value, error):
        if error:
            results["errors"].append(error)
        manager.windows["studio"].run_tests()
        state["stage"] = 5

    QTimer.singleShot(350, lambda: bridge.call("studio.stop", stopped, session_id=value["session_id"]))


def agent_start(value):
    bridge.call(
        "agent.run",
        result_callback("Agent task persists", chat_start),
        request="list files in " + str(workspace),
        workspace_id=state["workspace_id"],
    )


def chat_start(value):
    manager.open("chat")
    bridge.call("chat.get", chat_loaded)


def chat_loaded(value, error):
    if error:
        results["errors"].append(error)
        finish()
        return
    state["chat_id"] = value["id"]
    chat = manager.windows["chat"]
    chat.render(value)
    if args.live_model:

        def configured(snapshot, error):
            if error:
                results["errors"].append(error)
                finish()
                return
            params = dict(snapshot["params"])
            params["max_tokens"] = 32
            bridge.call(
                "data.save_settings",
                lambda v, e: send_chat(),
                chat_id=state["chat_id"],
                settings=snapshot["settings"],
                params=params,
                system_prompt="You are OLIVE. Reply briefly.",
                alias="",
            )

        bridge.call("data.settings", configured, chat_id=state["chat_id"])
    else:
        send_chat()


def send_chat():
    state["stage"] = 7
    bridge.call(
        "interaction.submit", chat_done, chat_id=state["chat_id"], text="Say OLIVE desktop is ready in one sentence."
    )


def chat_done(value, error):
    record("Chat streamed", state["stream_events"] > 0 and not error)
    record("Natural-language front door routes to streamed Chat", state["stream_events"] > 0 and not error)
    if error:
        results["errors"].append(error)
    chat = manager.windows["chat"]
    chat.grab().save(str(output / "chat.png"))
    chat.close()
    record("singleton reopen retains state", manager.open("chat") is chat)
    state["stage"] = 8
    bridge.call(
        "chat.send", stopped_chat, chat_id=state["chat_id"], text="Count slowly from one to one hundred."
    )


def stopped_chat(value, error):
    record("Stop generation", not error)
    finish()


def events(topic, value):
    if topic == "chat_stream":
        state["stream_events"] += 1
        if state["stage"] == 8:
            bridge.call("chat.stop", chat_id=state["chat_id"])
    if topic == "notification" and value.get("kind") == "error":
        results["errors"].append(value["message"])


bridge.event.connect(events)


def finish():
    if state["shutdown"]:
        return
    state["shutdown"] = True
    from olive.research.models import ResearchSession, ResearchSource
    from olive.research.extraction import extract_page
    from olive.research.evidence import extract_evidence
    from olive.research.citations import render_report

    page = extract_page(
        "<p>Embeddings represent text for semantic retrieval.</p>", "https://example.com/docs"
    )
    source = ResearchSource(page.url, "Research smoke fixture", status="read", content_hash=page.content_hash)
    session = ResearchSession("How do embeddings support retrieval?", status="completed")
    session.sources = [source]
    session.evidence = extract_evidence(page, source.id, [session.question])
    session.findings = [
        {"text": session.evidence[0].quote, "kind": "source_claim", "evidence_ids": [session.evidence[0].id]}
    ]
    session.final_report = render_report(
        session.question, session.findings, session.sources, session.evidence
    )
    research = manager.open("research")
    research.render(session.to_dict())
    research.sources.selectRow(0)
    record("Research evidence inspector", "semantic retrieval" in research.evidence.toPlainText())
    research.grab().save(str(output / "research.png"))
    manager.open("home")
    record("Research singleton state", manager.open("research").session["id"] == session.id)
    record(
        "system tray actions",
        manager.tray is not None
        and {"Open OLIVE", "Open Chat", "Open Agent", "Open Studio", "Open Research", "Exit"}.issubset(
            {action.text() for action in manager.tray_menu.actions()}
        ),
    )
    record("workspaces share bridge", len({id(w.bridge) for w in manager.windows.values()}) == 1)
    studio = manager.pages["studio"]
    editor = studio.tabs.currentWidget()
    next(action for action in manager.tray_menu.actions() if action.text() == "Open Studio").trigger()
    record("tray navigates existing main window", manager.main.stack.currentWidget() is studio and studio.window() is manager.main)
    record("Studio retains editor through navigation", studio.tabs.currentWidget() is editor and studio.workspace_id == state["workspace_id"])
    shared = bridge.worker.services
    identities = (id(shared), id(shared.ollama), id(shared.agent))
    shell = manager.main
    for feature in ("home", "studio", "research", "chat", "studio"):
        manager.open(feature)
    record("Home Studio Research Chat Studio retains shared state", manager.main is shell and
           studio.tabs.currentWidget() is editor and studio.workspace_id == state["workspace_id"] and
           identities == (id(bridge.worker.services), id(bridge.worker.services.ollama), id(bridge.worker.services.agent)))
    from olive.agent.confirmation_service import ConfirmationRequest
    from olive.ui_qt.dialogs.confirmation import ConfirmationDialog
    from PySide6.QtWidgets import QPlainTextEdit, QDialogButtonBox
    store_report = output / "store-preview.json"
    store_bytes = store_report.read_bytes() if store_report.exists() else b""
    store_encoding = "utf-16" if store_bytes.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    for permission, details, button in (("communication.send", {"destination": "alex@example.test", "body": "Unsent fixture"}, "Send"),
                                        ("software.install", json.loads(store_bytes.decode(store_encoding))["preview"] if store_bytes else
                                         {"application": "Fixture", "publisher": "Fixture", "source": "Local test", "cost": "free"}, "Install")):
        dialog = ConfirmationDialog(ConfirmationRequest("smoke", permission, "Review exact action", "high", ["Acceptance"], arguments=details), manager.main)
        dialog.show()
        APP = application.qt
        APP.processEvents()
        record(permission + " semantic Qt preview", button in [b.text() for b in dialog.findChild(QDialogButtonBox).buttons()] and
               all(str(value) in dialog.findChild(QPlainTextEdit).toPlainText() for value in details.values()))
        dialog.reject()
        record(permission + " preview cancellation denies action", not dialog.response.approved)
    chat = manager.open("chat")
    chat.pending_draft.render({"state": "prepared", "entities": {"application": "Fixture Messenger",
        "server": "Example", "channel": "news", "message": "Unsent preview fixture"}})
    record("unsent draft card preserves destination and content", "Example" in chat.pending_draft.destination.text()
           and "news" in chat.pending_draft.destination.text() and chat.pending_draft.body.toPlainText() == "Unsent preview fixture")
    chat.pending_draft.render({"state": "verification_pending", "submission_uncertain": True,
        "entities": {"channel": "news", "message": "Unsent preview fixture"}})
    record("unverified submission blocks repeat send and edit", all(not button.isEnabled()
           for button in chat.pending_draft.action_buttons) and "Check message delivery" in chat.pending_draft.title())
    chat.pending_draft.render(None)
    record("cancelled draft card is hidden", chat.pending_draft.isHidden())
    chat.composer.setPlainText("Unsent navigation fixture")
    popout = manager.popout("chat")
    record("explicit popout reuses workspace", popout.centralWidget() is chat and chat.window() is popout)
    popout.close()
    record("popout returns with draft intact", chat.window() is manager.main and chat.composer.toPlainText() == "Unsent navigation fixture")
    desktop = manager.open("desktop")
    from PySide6.QtWidgets import QPushButton
    desktop.findChild(QPushButton, "desktopStopControl").click()
    record("desktop emergency stop is immediate", bridge.worker.services.desktop.stop_event.is_set())
    results["elapsed_seconds"] = round(time.monotonic() - state["started"], 2)
    manager.exit()


bridge.ready.connect(initialize)
timer = QTimer()
timer.timeout.connect(tick)
timer.start(100)
application.run()
record("clean shutdown", not bridge.worker.isRunning())
(output / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print("Smoke results saved", flush=True)
# Keep screenshot artifacts only, discard all temporary application data.
temporary.cleanup()
raise SystemExit(1 if results["errors"] or not all(results["checks"].values()) else 0)
