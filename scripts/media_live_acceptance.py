"""Explicit system-media inspection; optional pause, never unattended playback."""

import asyncio
import json
from pathlib import Path
import sys
import tempfile
import os
import wave
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse


async def main():
    with tempfile.TemporaryDirectory(prefix="olive-media-acceptance-") as directory:
        async def approve(request):
            return ConfirmationResponse(request.tool_name in {"desktop.inspect_application", "application.media"})
        services = ServiceContainer(lambda *args: None, approve, data_dir=directory, migrate=False)
        try:
            services.desktop.configure({"enabled": True})
            if "--silent-file" in sys.argv:
                from olive.desktop.windows_observation import enumerate_windows
                before = enumerate_windows()
                if any("zunemusic" in w.get("package_identity", "").casefold() for w in before):
                    raise RuntimeError("Media Player is already open; leave the user's session untouched")
                source = Path(directory) / "OLIVE silent acceptance.wav"
                with wave.open(str(source), "wb") as output:
                    output.setnchannels(1)
                    output.setsampwidth(2)
                    output.setframerate(8000)
                    output.writeframes(b"\0\0" * 8000 * 60)
                os.startfile(str(source))
                try:
                    for _ in range(60):
                        sessions = await services.desktop.media_sessions()
                        candidates = [s for s in sessions if "zunemusic" in s["application_id"].casefold()]
                        if len(candidates) == 1:
                            break
                        await asyncio.sleep(.2)
                    else:
                        raise RuntimeError("Default player did not expose a compatible system media session")
                    app_id = candidates[0]["application_id"]
                    paused = await services.desktop.media_action(app_id, "pause")
                    played = await services.desktop.media_action(app_id, "play")
                    stopped = await services.desktop.media_action(app_id, "pause")
                    print(json.dumps({"application": "Windows Media Player", "silent_local_file": True,
                                      "pause": paused, "play": played, "final_pause": stopped}), flush=True)
                    return
                finally:
                    import win32gui
                    import win32con
                    owned = [w for w in enumerate_windows() if "zunemusic" in w.get("package_identity", "").casefold()
                             and w["hwnd"] not in {old["hwnd"] for old in before}]
                    for window in owned:
                        win32gui.PostMessage(window["hwnd"], win32con.WM_CLOSE, 0, 0)
                    for _ in range(50):
                        if not any(win32gui.IsWindow(w["hwnd"]) for w in owned):
                            break
                        await asyncio.sleep(.1)
            sessions = await services.desktop.media_sessions()
            result = {"provider": services.desktop.media.provider.name, "sessions": sessions}
            if "--pause" in sys.argv:
                candidates = [session for session in sessions if "applemusic" in session["application_id"].casefold()]
                if len(candidates) != 1:
                    raise ValueError("One Apple Music media session is required for the explicit pause test")
                result["pause"] = await services.desktop.media_action(candidates[0]["application_id"], "pause")
            print(json.dumps(result))
        finally:
            await services.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
