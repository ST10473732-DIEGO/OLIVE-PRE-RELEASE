"""One confirmed editor submission; no raw-input or model-authorized send path."""

import asyncio
import secrets
import time
from .action_preview import ActionPreview
from .target_resolver import DesktopTargetResolver
from .workflow import DesktopStep
from .verification import within


def destination_text(controls, targets):
    if not isinstance(targets, list) or not 1 <= len(targets) <= 3:
        raise ValueError("Select bounded destination evidence")
    parts = []
    for target in targets:
        control = DesktopTargetResolver().resolve(controls, target)
        if control.get("password"):
            raise PermissionError("Secret controls cannot be destination evidence")
        part = control.get("value") or control.get("name", "")
        if not part.strip():
            raise ValueError("The destination evidence is empty")
        parts.append(part)
    return " | ".join(parts)


async def submit_editor_message(desktop, target, bindings):
    if not desktop.sessions or not desktop.sessions.current:
        raise ValueError("Inspect the intended conversation first")
    if (not isinstance(bindings, dict) or set(bindings) != {"destination", "body"} or bindings["body"] != target
            or not isinstance(bindings["destination"], list)):
        raise ValueError("The submission target must be the reviewed message body")
    if target in bindings["destination"]:
        raise ValueError("The body cannot prove its own destination")
    session = desktop.sessions.sessions[desktop.sessions.current]
    gateway = desktop.gateway
    gateway.require_uia()
    if gateway.settings()["keyboard_policy"] == "deny":
        raise PermissionError("Keyboard input is disabled")
    before = await gateway.observe(session, control_limit=1200, depth_limit=24)
    if before.get("truncated"):
        raise ValueError("The conversation snapshot is incomplete. Narrow the view before reviewing a send.")
    session.observe(before)
    body = DesktopTargetResolver().resolve(before["controls"], target)
    text = body.get("value", "")
    if (body.get("control_type") != "Edit" or body.get("password") or not body.get("enabled")
            or not body.get("visible") or not isinstance(text, str) or not 1 <= len(text) <= 4000):
        raise ValueError("Select a visible, non-secret message editor with a bounded draft")
    destination = destination_text(before["controls"], bindings["destination"])
    preview = ActionPreview.create(session.identity.id, "communication.send", {
        "destination": destination, "body": text, "submission": "Press Enter in the reviewed message editor"})
    await gateway.approval(session, "desktop.control_application", "Control the selected application", {
        "application": session.identity.display_name, "target": body["name"]})
    await gateway.approval(session, "desktop.keyboard_input", "Submit the reviewed message with Enter", {
        "application": session.identity.display_name, "target": body["name"]}, always=True)
    await gateway.approval(session, "communication.send", "Send this message?", preview.details, always=True)
    after = await gateway.observe(session, control_limit=1200, depth_limit=24)
    if after.get("truncated"):
        raise PermissionError("The conversation snapshot became incomplete after review; no message was submitted")
    current_body = DesktopTargetResolver().resolve(after["controls"], target)
    if (current_body.get("value") != text or current_body.get("name") != body.get("name")
            or current_body.get("control_type") != "Edit" or current_body.get("password")
            or not current_body.get("visible") or not current_body.get("enabled")
            or destination_text(after["controls"], bindings["destination"]) != destination):
        raise PermissionError("The destination or body changed after send approval")
    session.observe(after)
    seen = {c.get("runtime_id") for c in after["controls"]}
    step = DesktopStep(session.key, "submit_message", target, {"text": text,
                       "destination": bindings["destination"], "destination_text": destination},
                       {"runtime_id": current_body["runtime_id"], "value": ""}, "communication.send")
    permit = secrets.token_hex(24)
    gateway.permits[permit] = gateway.fingerprint(session, step)
    try:
        await gateway.execute(session, step, permit, desktop.stop_event)
        # No replay on timeout. Require both a cleared composer and new visible
        # message content, never an older matching message or an empty field alone.
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            gateway.check()
            observation = await gateway.observe(session, control_limit=1200, depth_limit=24)
            if observation.get("truncated"):
                raise TimeoutError("Submission was requested once but the conversation snapshot is incomplete; check the application")
            session.observe(observation)
            controls = observation["controls"]
            if destination_text(controls, bindings["destination"]) != destination:
                raise PermissionError("The conversation changed after submission; check it before retrying")
            editor = DesktopTargetResolver().resolve(controls, target)
            receipts = [c for c in controls if c.get("runtime_id") not in seen and c.get("runtime_id")
                        and not within(c, editor["runtime_id"], controls)
                        and c.get("visible") and c.get("control_type") in {"Text", "ListItem", "Group"}
                        and (c.get("value") or c.get("name", "")).strip() == text.strip()]
            if editor.get("value") == "" and receipts:
                desktop.observation = observation
                desktop.record.status = "completed"
                desktop.record.verification = "New message content appeared and the reviewed editor cleared"
                desktop.publish()
                return {"verified": True, "permission": "communication.send", "evidence": "new_message_and_cleared_editor"}
            await asyncio.sleep(.1)
        raise TimeoutError("Submission was requested once but delivery was not verified; inspect the conversation before any retry")
    except Exception as error:
        raise TimeoutError("Submission may have occurred; inspect the conversation before any retry") from error
