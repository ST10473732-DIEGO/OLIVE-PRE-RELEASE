"""Local-only Chromium editor typing/submission acceptance; no account or external destination."""

import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse
from olive.desktop.browser_focus import profile_windows


class Page(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'''<!doctype html><title>OLIVE native editor fixture</title>
        <div id="editor" contenteditable="true" role="textbox" aria-label="Local message editor"
             style="border:1px solid black; width:500px; height:80px"></div>
        <div id="filler" style="width:500px;height:80px;overflow:hidden"></div><div id="messages"></div>
        <script>
        for (let i=0;i<350;i++) {
          const button=document.createElement('button'); button.textContent='Fixture '+i;
          button.style='width:5px;height:5px;padding:0;font-size:1px'; filler.appendChild(button);
        }
        let draft = ''; window.inputEvents = 0; window.submissions = 0;
        editor.addEventListener('input', () => { draft = editor.textContent; window.inputEvents++; });
        editor.addEventListener('keydown', event => {
          if (event.key === 'Enter') {
            event.preventDefault();
            if (draft.trim()) {
              const message = document.createElement('p'); message.textContent = draft;
              messages.appendChild(message); editor.textContent = ''; draft = ''; window.submissions++;
            }
          }
        });
        </script>'''
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


async def main():
    server = HTTPServer(("127.0.0.1", 0), Page)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    reviewed = False
    async def review(request):
        nonlocal reviewed
        if request.tool_name == "communication.send":
            allowed = (not reviewed and request.arguments.get("body") == "hello"
                       and request.arguments.get("destination", "").startswith("OLIVE native editor fixture"))
            reviewed = reviewed or allowed
            return ConfirmationResponse(allowed)
        return ConfirmationResponse(request.tool_name in {"network.read", "desktop.control_application",
            "desktop.inspect_application", "desktop.keyboard_input", "desktop.mouse_input"})
    try:
        with tempfile.TemporaryDirectory(prefix="olive-native-editor-") as directory:
            services = ServiceContainer(lambda *args: None, review, data_dir=directory, migrate=False)
            try:
                desktop = services.desktop
                desktop.configure({"enabled": True, "keyboard_policy": "ask", "mouse_policy": "ask"})
                tabs = await desktop.browser_launch("chrome")
                await desktop.browser_navigate(tabs[0]["id"], f"http://127.0.0.1:{server.server_port}")
                windows = profile_windows(desktop.browser.provider.profile)
                if len(windows) != 1:
                    raise AssertionError("Owned browser window is ambiguous")
                await desktop.list_windows()
                key = next(key for key, value in desktop.windows.items() if value["hwnd"] == windows[0]["hwnd"])
                state = await desktop.inspect(key)
                controls = state["observation"]["controls"]
                for _ in range(30):
                    editors = [c for c in controls if c.get("name") == "Local message editor" and c["control_type"] == "Edit"]
                    if len(editors) == 1:
                        break
                    await asyncio.sleep(.1)
                    session = desktop.sessions.sessions[desktop.sessions.current]
                    controls = (await desktop.gateway.observe(session))["controls"]
                else:
                    print(json.dumps({"owned_fixture_controls": [{"name": c["name"], "type": c["control_type"]} for c in controls]}), flush=True)
                    raise AssertionError("The owned rich editor was not exposed through UIA")
                body = editors[0]
                title = next(c for c in controls if c["control_type"] == "Window")
                target = {"runtime_id": body["runtime_id"]}
                await desktop.perform("set_text", target, {"text": "earlier draft", "pointer_focus": True,
                    "expected_previous": ""}, {**target, "value": "earlier draft"})
                await desktop.perform("set_text", target, {"text": "hello", "pointer_focus": True,
                    "expected_previous": "earlier draft"}, {**target, "value": "hello"})
                page = desktop.browser.provider.pages[tabs[0]["id"]]
                events = await page.evaluate("window.inputEvents")  # Fixed fixture-only read; never model-generated script.
                if not events:
                    raise AssertionError("Typed text did not reach the editor's input state")
                result = await desktop.consequence("communication.send", target, {
                    "destination": [{"runtime_id": title["runtime_id"]}], "body": target},
                    {**target, "value": ""}, method="editor_enter")
                count = await page.evaluate("window.submissions")
                if not result.get("verified") or count != 1:
                    raise AssertionError("Local editor submission was not verified exactly once")
                session = desktop.sessions.sessions[desktop.sessions.current]
                observed = await desktop.gateway.observe(session, control_limit=1200, depth_limit=24)
                receipt_indexes = [index for index, c in enumerate(observed["controls"])
                                   if c.get("control_type") == "Text" and c.get("name") == "hello"]
                if not receipt_indexes or min(receipt_indexes) < 300:
                    raise AssertionError("Fixture did not exercise a message beyond the ordinary observation limit")
                print(json.dumps({"chromium_input_events_verified": True, "local_submission_count": count,
                                  "reviewed_draft_replacement_verified": True,
                                  "message_beyond_ordinary_snapshot_verified": True,
                                  "semantic_send_reviewed": reviewed, "external_message_sent": False}), flush=True)
            finally:
                await services.shutdown()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    asyncio.run(main())
