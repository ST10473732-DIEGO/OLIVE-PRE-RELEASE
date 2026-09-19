"""Opt-in Discord acceptance. Sending is denied unless --allow-send is explicit.

Uses temporary OLIVE data. Does not close Discord or remove any existing draft.
No screenshots, accessible page bodies, or unrelated messages are logged.
"""

import argparse
import asyncio
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse


async def main(channel="general", observe_only=False, allow_send=False, verify_existing=False):
    previews = []
    send_approved = False
    async def review(request):
        nonlocal send_approved
        if request.tool_name == "communication.send":
            import re
            destination = str(request.arguments.get("destination", "")).casefold()
            exact = (request.arguments.get("body") == "hello" and bool(request.targets)
                     and all("discord" in target.casefold() for target in request.targets)
                     and all(re.search(r"(?<!\w)" + re.escape(name.casefold()) + r"(?!\w)", destination)
                             for name in ("guaplings", channel)))
            approved = bool(allow_send and not send_approved and exact)
            send_approved = send_approved or approved
            previews.append({"type": request.tool_name, "server": "Guaplings", "channel": channel,
                             "message": "hello" if exact else "[unexpected preview]", "reviewed": approved})
            print(json.dumps({"semantic_send_preview": previews[-1]}), flush=True)
            return ConfirmationResponse(approved)
        allowed = {"system.open_application", "desktop.inspect_application", "desktop.control_application", "desktop.keyboard_input", "desktop.mouse_input"}
        return ConfirmationResponse(request.tool_name in allowed and bool(request.targets)
                                    and all("discord" in target.casefold() for target in request.targets))
    with tempfile.TemporaryDirectory(prefix="olive-language-acceptance-") as directory:
        services = ServiceContainer(lambda *args: None, review, data_dir=directory, migrate=False)
        try:
            services.desktop.configure({"enabled": True, "keyboard_policy": "ask", "mouse_policy": "ask"})
            await services.model_registry.refresh()
            interpreted = []
            execute = services.interaction.router.execute
            async def record_step(step, context):
                interpreted.append(step)
                return await execute(step, context)
            services.interaction.router.execute = record_step
            if observe_only or verify_existing:
                await services.desktop.discover_applications()
                opening = await services.desktop.open_application(services.desktop.discovery.resolve("Discord").id)
                result = {"messages": [{"content": "Observation complete" if opening.get("verified") else opening.get("message", "Discord was not verified")}]}
            else:
                result = await services.interaction.submit(
                    f"open discord and go to the guaplings server in the #{channel} channel and send a message saying hello")
            context = services.interaction.context(services.current_chat_id)
            from olive.desktop.application_launch import matches
            from olive.desktop.application_discovery import AmbiguousApplication
            try:
                application = services.desktop.discovery.resolve("Discord")
            except AmbiguousApplication:
                application = None
            windows = [w for w in services.desktop.windows.values() if application and matches(application, w)]
            observation = services.desktop.observation
            if services.desktop.sessions and services.desktop.sessions.current:
                session = services.desktop.sessions.sessions[services.desktop.sessions.current]
                observation = await services.desktop.gateway.observe(session, **(
                    {"control_limit": 1200, "depth_limit": 24} if verify_existing else {}))
                session.observe(observation)
            controls = observation.get("controls", [])
            from olive.desktop.verification import contains_destination, within
            editors = [c for c in controls if c.get("control_type") == "Edit" and channel.casefold() in c.get("name", "").casefold()]
            receipts = [c for c in controls if c.get("control_type") == "Text" and c.get("visible") and c.get("name", "").strip() == "hello"
                        and all(not within(c, editor["runtime_id"], controls) for editor in editors)]
            title = observation.get("window", {}).get("title", "")
            destination_verified = all(contains_destination(title, name) for name in ("guaplings", channel))
            existing_verified = (destination_verified and not observation.get("truncated") and len(receipts) == 1
                                 and len(editors) == 1 and not editors[0].get("value"))
            print(json.dumps({"test": "discord_existing_message_read_only" if verify_existing else
                "discord_natural_language_authorized_send" if allow_send else "discord_natural_language_prepare_only",
                "existing_message_verified": existing_verified if verify_existing else None,
                "interpreted_steps": interpreted,
                "control_count": len(controls),
                "visible_send_controls": sum(1 for c in controls if c.get("visible") and "invoke" in c.get("actions", [])
                    and c.get("name", "").strip().casefold() in {"send", "send message", "send now"}),
                "destination_edit_fields": sum(1 for c in controls if c.get("control_type") == "Edit"
                    and "set_text" in c.get("actions", []) and channel.casefold() in c.get("name", "").casefold()),
                "editor_content_state": [("empty" if not c.get("value", "").strip() else
                    "requested_body" if c.get("value", "").strip() == "hello" else "other_draft")
                    for c in controls if c.get("control_type") == "Edit" and channel.casefold() in c.get("name", "").casefold()],
                "editor_value_metadata": [{"length": len(c.get("value", "")),
                    "framework_id": c.get("framework_id"), "class_name": c.get("class_name"),
                    "equals_label": c.get("value") == c.get("name"), "null_value_text": c.get("value") == "None",
                    "formatting_only": all(ch.isspace() or __import__('unicodedata').category(ch) == "Cf" for ch in c.get("value", ""))}
                    for c in controls if c.get("control_type") == "Edit" and channel.casefold() in c.get("name", "").casefold()],
                "visible_test_body_evidence": [{"control_type": c.get("control_type"),
                    "exact_body": (c.get("value") or c.get("name", "")).strip() == "hello"}
                    for c in controls if c.get("visible") and c.get("control_type") != "Edit"
                    and __import__('re').search(r"(?<!\w)hello(?!\w)", (c.get("value") or c.get("name", "")).casefold())],
                "matching_window_count": len(windows), "launch_mechanism": application.launch_mechanism if application else "ambiguous",
                "window_states": [{**{key: w.get(key) for key in ("foreground", "minimized", "window_class", "owner_hwnd")},
                    "requested_server_in_title": "guaplings" in w.get("title", "").casefold(),
                    "requested_channel_in_title": channel.casefold() in w.get("title", "").casefold()} for w in windows],
                "requested_target_evidence": [{"requested": name, "matches": [
                    {"control_type": c.get("control_type"), "actions": c.get("actions"), "tree_index": index,
                     "exact_plain_name": c.get("name", "").casefold() == name,
                     "exact_hash_name": c.get("name", "").casefold() == "#" + name,
                     "selected": c.get("selected")}
                    for index, c in enumerate(controls) if name in c.get("name", "").casefold()]}
                    for name in ("guaplings", channel.casefold())],
                "send_confirmation_reached": bool(previews), "send_approved": send_approved,
                "draft_state": (context.pending or {}).get("state"),
                "result": result["messages"][-1]["content"]}), flush=True)
            if verify_existing:
                return existing_verified and not send_approved
            if observe_only:
                return bool(controls and windows)
            if allow_send:
                return destination_verified and (context.pending or {}).get("state") == "sent"
            return (destination_verified and len(previews) == 1 and previews[0]["message"] == "hello"
                    and not send_approved and (context.pending or {}).get("state") == "awaiting_confirmation")
        finally:
            await services.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discord-navigation", required=True, action="store_true")
    parser.add_argument("--channel", default="general")
    parser.add_argument("--observe-only", action="store_true")
    parser.add_argument("--verify-existing", action="store_true", help="Read-only check of one visible hello and an empty composer; never send")
    parser.add_argument("--allow-send", action="store_true", help="Explicitly authorize ONE hello message to the selected Guaplings channel")
    args = parser.parse_args()
    channel = args.channel.lstrip("#")
    if not channel or len(channel) > 100 or any(c in channel for c in "\r\n"):
        parser.error("Enter one bounded channel name")
    if args.allow_send and (args.observe_only or args.verify_existing):
        parser.error("Observation-only mode cannot authorize sending")
    raise SystemExit(0 if asyncio.run(main(channel, args.observe_only, args.allow_send, args.verify_existing)) else 1)
