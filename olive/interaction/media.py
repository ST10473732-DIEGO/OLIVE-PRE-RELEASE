"""Named media requests use accessible search and independently verified playback."""

import asyncio
import re
import time
from ..desktop.workflow import DesktopStep
from ..desktop.target_resolver import normalized


class MediaRequest:
    def __init__(self, desktop):
        self.desktop = desktop

    async def play(self, query, application=""):
        d = self.desktop
        sessions = await d.media_sessions()
        matches = [s for s in sessions if not application or normalized(application).replace(" ", "") in
                   normalized(s["application_id"]).replace(" ", "")]
        if len(matches) != 1:
            raise ValueError("Which music application should play that song?")
        media = matches[0]
        await d.list_windows()
        windows = [key for key, window in d.windows.items() if window["application"].casefold() in media["application_id"].casefold()]
        if len(windows) != 1:
            raise ValueError("Please select the music application's window so I can search its library.")
        state = await d.inspect(windows[0])
        controls = state["observation"]["controls"]
        results = self.results(controls, query)
        if not results:
            search = [c for c in controls if c.get("control_type") == "Edit" and not c.get("password")
                      and c.get("visible") and c.get("enabled") and re.search(r"\bsearch\b", c.get("name", ""), re.I)]
            if len(search) != 1:
                raise ValueError("I couldn't identify one accessible music search field.")
            await d.perform("search", {"runtime_id": search[0]["runtime_id"]}, {"text": query}, {"name": query})
        session = d.sessions.sessions[d.sessions.current]
        before = await d.gateway.observe(session)
        session.observe(before)
        results = self.results(before["controls"], query)
        if len(results) != 1:
            raise ValueError("Several or no exact song results are available. Please identify the artist or intended result.")
        target = {"runtime_id": results[0]["runtime_id"]}
        step = DesktopStep(session.key, "invoke", target, {}, {"name": query}, "desktop.control_application")
        permit = await d.gateway.authorize(session, step)
        await d.gateway.execute(session, step, permit, d.stop_event)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            d.gateway.check()
            current = await d.media_sessions()
            playing = [s for s in current if s["application_id"] == media["application_id"]
                       and str(s.get("state", s.get("playback_state", ""))).casefold() == "playing"
                       and normalized(s.get("title", "")) == normalized(query)]
            if len(playing) == 1:
                return f"{query} is playing."
            await asyncio.sleep(.25)
        raise ValueError("The song action was requested, but playback of that exact title was not verified.")

    @staticmethod
    def results(controls, query):
        return [c for c in controls if normalized(c.get("name", "")) == normalized(query)
                and c.get("visible") and c.get("enabled") and "invoke" in c.get("actions", [])]
