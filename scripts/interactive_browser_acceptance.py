"""Explicit live browser acceptance on a temporary loopback page; no accounts."""

import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import io
import wave
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse


class Page(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/silence.wav":
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as sound:
                sound.setnchannels(1)
                sound.setsampwidth(2)
                sound.setframerate(8000)
                sound.writeframes(b"\0\0" * 8000 * 60)
            data = buffer.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path == "/download":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Disposition", 'attachment; filename="fixture.txt"')
            self.end_headers()
            self.wfile.write(b"OLIVE download fixture")
            return
        body = b'''<!doctype html><title>OLIVE interactive acceptance</title>
        <label>Message <input aria-label="Message"></label>
        <button onclick="this.textContent='Verified'">Preview</button>
        <input aria-label="Recipient"><input aria-label="Subject">
        <textarea aria-label="Body"></textarea>
        <input type="file" aria-label="Attachment">
        <button onclick="this.textContent='Sent fixture'">Send</button>
        <a href="/download">Download fixture</a>
        <audio id="audio" src="/silence.wav" loop></audio>
        <button onclick="audio.play();this.textContent='Audio started'">Play silent audio</button>
        <button onclick="if (!confirm('OLIVE untrusted modal fixture')) this.textContent='Modal dismissed'">Open test modal</button>
        <div style="height:1800px"></div><button>Scroll target</button>
        <script>
        navigator.mediaSession.metadata = new MediaMetadata({title:'OLIVE silent acceptance'});
        navigator.mediaSession.setActionHandler('play', () => audio.play());
        navigator.mediaSession.setActionHandler('pause', () => audio.pause());
        audio.onplay = () => navigator.mediaSession.playbackState = 'playing';
        audio.onpause = () => navigator.mediaSession.playbackState = 'paused';
        </script>'''
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return  # The fixture intentionally emits no request logs.


async def main():
    server = HTTPServer(("127.0.0.1", 0), Page)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="olive-interactive-acceptance-") as folder:
            async def approve(request):
                url = request.arguments.get("url", "")
                return ConfirmationResponse(not url or url.startswith("http://127.0.0.1:"))
            services = ServiceContainer(lambda *args: None, approve, data_dir=folder, migrate=False)
            try:
                services.desktop.configure({"enabled": True, "keyboard_policy": "ask"})
                tabs = await services.desktop.browser_launch("chrome")
                state = await services.desktop.browser_navigate(tabs[0]["id"], "http://127.0.0.1:" + str(server.server_port))
                field = next(item for item in state["controls"] if item["name"] == "Message")
                if "--natural" in sys.argv:
                    await services.model_registry.refresh()
                    context = services.interaction.context(services.current_chat_id)
                    context.tab_id, context.browser_application = tabs[0]["id"], "Chrome"
                    context.entities["application"] = "Chrome"
                    result = await services.interaction.submit("Please put Hello from OLIVE in the Message field.")
                    state = await services.desktop.browser_observe(tabs[0]["id"])
                    field = next(item for item in state["controls"] if item["name"] == "Message")
                    actual = await services.desktop.browser.execute("field_value", target_id=field["id"])
                    if actual != "Hello from OLIVE":
                        print(json.dumps({"interpretation": services.interaction.inspect(services.current_chat_id), "actual_fixture_text": actual}), flush=True)
                        raise AssertionError("Natural-language browser fill failed: " + result["messages"][-1]["content"])
                else:
                    state = await services.desktop.browser_action(field["id"], "fill", "Hello from OLIVE")
                button = next(item for item in state["controls"] if item["name"] == "Preview")
                state = await services.desktop.browser_action(button["id"], "click", expected="Verified")
                click_verified = state["verified"]
                draft_fields = (("Recipient", "alex@example.test"), ("Subject", "Local acceptance"), ("Body", "Fixture only; no external communication"))
                if "--natural" in sys.argv:
                    result = await services.interaction.submit(
                        'Prepare an unsent email to alex@example.test with subject "Local acceptance" and body "Fixture only; no external communication".')
                    state = await services.desktop.browser_observe(context.tab_id)
                    for label, value in draft_fields:
                        field = next(item for item in state["controls"] if item["name"] == label)
                        if await services.desktop.browser.execute("field_value", target_id=field["id"]) != value:
                            print(json.dumps({"draft_interpretation": services.interaction.inspect(services.current_chat_id)}), flush=True)
                            raise AssertionError("Natural email draft preparation failed: " + result["messages"][-1]["content"])
                else:
                    for label, value in draft_fields:
                        field = next(item for item in state["controls"] if item["name"] == label)
                        state = await services.desktop.browser_action(field["id"], "fill", value)
                attachment = Path(folder) / "fixture.txt"
                attachment.write_text("Local attachment fixture", encoding="utf-8")
                upload = next(item for item in state["controls"] if item["name"] == "Attachment")
                if "--natural" in sys.argv:
                    result = await services.interaction.submit(f'Find fixture.txt in "{folder}".')
                    if context.entities.get("path") != str(attachment):
                        raise AssertionError("Natural file lookup failed: " + result["messages"][-1]["content"])
                    from cross_application_acceptance import return_to_browser
                    await return_to_browser(services, context)
                    result = await services.interaction.submit("Attach that file.")
                    if await services.desktop.browser.provider.attachment_names(context.tab_id) != [attachment.name]:
                        raise AssertionError("Natural cross-feature attachment failed: " + result["messages"][-1]["content"]
                                             + "; interpretation=" + repr(context.last_interpretation))
                    state = await services.desktop.browser_observe(context.tab_id)
                else:
                    state = await services.desktop.browser_upload(upload["id"], str(attachment))
                fields = {key: next(item["id"] for item in state["controls"] if item["name"] == label)
                          for key, label in (("destination", "Recipient"), ("subject", "Subject"), ("body", "Body"), ("send", "Send"))}
                state = await services.desktop.browser_send(fields, "Sent fixture")
                link = next(item for item in state["controls"] if item["name"] == "Download fixture")
                downloaded = await services.desktop.browser_download(link["id"])
                destination = Path(folder) / "saved-fixture.txt"
                await services.desktop.save_download(downloaded["download"]["id"], str(destination))
                if destination.read_bytes() != b"OLIVE download fixture":
                    raise AssertionError("Quarantine to filesystem handoff did not preserve bytes")
                workflow_destination = Path(folder) / "workflow-fixture.txt"
                await services.desktop.universal.run("Local browser and filesystem acceptance", [
                    {"operation": "folder.open", "arguments": {"path": folder}},
                    {"operation": "browser.open", "arguments": {"channel": "chrome", "url": "http://127.0.0.1:" + str(server.server_port)}},
                    {"operation": "browser.act", "arguments": {"action": "fill", "target": "Message", "text": "Workflow fixture", "expected": ""}},
                    {"operation": "browser.download", "arguments": {"target": "Download fixture"}},
                    {"operation": "download.save", "arguments": {"destination": str(workflow_destination)}},
                ])
                if workflow_destination.read_bytes() != b"OLIVE download fixture":
                    raise AssertionError("Composed browser/filesystem workflow did not preserve bytes")
                if "--media" in sys.argv:
                    before = {s["application_id"] for s in await services.desktop.media_sessions()}
                    state = await services.desktop.browser_observe(tabs[0]["id"])
                    play = next(c for c in state["controls"] if c["name"] == "Play silent audio")
                    await services.desktop.browser_action(play["id"], "click", expected="Audio started")
                    for _ in range(30):
                        candidates = [s for s in await services.desktop.media_sessions() if s["application_id"] not in before]
                        if len(candidates) == 1:
                            break
                        await asyncio.sleep(.2)
                    else:
                        raise RuntimeError("Chrome did not expose a unique new media session")
                    app = candidates[0]["application_id"]
                    pause = await services.desktop.media_action(app, "pause")
                    play = await services.desktop.media_action(app, "play")
                    final = await services.desktop.media_action(app, "pause")
                    print(json.dumps({"real_chrome_media_session": True, "pause": pause["verified"],
                                      "play": play["verified"], "final_pause": final["verified"]}), flush=True)
                state = await services.desktop.browser_observe(tabs[0]["id"])
                target = next(c for c in state["controls"] if c["name"] == "Scroll target")
                await services.desktop.browser_action(target["id"], "scroll")
                original = tabs[0]["id"]
                new_tabs = await services.desktop.browser_tab("new_tab", url="http://127.0.0.1:" + str(server.server_port))
                new_id = next(t["id"] for t in new_tabs if t["id"] != original)
                await services.desktop.browser_tab("switch_tab", tab_id=original)
                await services.desktop.browser_tab("close_tab", tab_id=new_id)
                state = await services.desktop.browser_observe(original)
                modal = next(c for c in state["controls"] if c["name"] == "Open test modal")
                from playwright.async_api import TimeoutError as BrowserTimeout
                try:
                    await services.desktop.browser_action(modal["id"], "click", expected="Modal dismissed")
                except (BrowserTimeout, PermissionError):
                    if not services.desktop.browser.provider.dialog_pending:
                        raise
                if not (await services.desktop.browser_dialog())["pending"]:
                    raise AssertionError("Unexpected modal did not pause browser control")
                await services.desktop.browser_dialog(dismiss=True)
                state = await services.desktop.browser_observe(original)
                if not any(c["name"] == "Modal dismissed" for c in state["controls"]):
                    raise AssertionError("Reviewed modal dismissal was not verified")
                print(json.dumps({"browser": "chrome", "interactive_profile": True, "fill_verified": True,
                                  "natural_language_fill_verified": "--natural" in sys.argv,
                                  "click_verified": click_verified, "research_provider_used": False,
                                  "attachment_selection_verified": True, "local_only_send_preview_verified": True,
                                  "natural_file_to_browser_attachment_verified": "--natural" in sys.argv,
                                  "natural_cross_application_return_preserves_file": "--natural" in sys.argv,
                                  "natural_browser_draft_preparation_verified": "--natural" in sys.argv,
                                  "quarantine_to_filesystem_verified": True, "composed_workflow_verified": True,
                                  "scroll_tabs_modal_verified": True}), flush=True)
            finally:
                await services.shutdown()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


if __name__ == "__main__":
    asyncio.run(main())
