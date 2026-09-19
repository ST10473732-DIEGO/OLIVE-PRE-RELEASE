"""Consequential UIA actions bind exact visible evidence to a one-time approval."""

import asyncio
import secrets
import time
from .action_preview import ActionPreview, REQUIRED_FIELDS
from .target_resolver import DesktopTargetResolver
from .workflow import DesktopStep


class DesktopConsequences:
    def __init__(self, desktop):
        self.desktop = desktop

    def details(self, session, controls, permission, bindings):
        required = set(REQUIRED_FIELDS.get(permission, ()))
        if permission not in {"software.install", "communication.send", "application.delete", "application.submit", "application.security_settings"}:
            raise PermissionError("This consequence requires a separate supported transaction flow")
        supplied = set(bindings)
        if permission == "software.install":
            required.discard("source")
        if supplied != required:
            raise ValueError("Select the visible evidence for every consequence field")
        result = {}
        for name, target in bindings.items():
            if name == "destination" and isinstance(target, list):
                if not 1 <= len(target) <= 3:
                    raise ValueError("A bounded destination evidence selection is required")
                parts = []
                for item in target:
                    control = DesktopTargetResolver().resolve(controls, item)
                    if control.get("password"):
                        raise PermissionError("Secret controls cannot be included in a consequence preview")
                    text = control.get("value") or control.get("name", "")
                    if not text.strip():
                        raise ValueError("Destination evidence is empty")
                    parts.append(text)
                result[name] = " | ".join(parts)
                continue
            control = DesktopTargetResolver().resolve(controls, target)
            if control.get("password"):
                raise PermissionError("Secret controls cannot be included in a consequence preview")
            result[name] = control.get("value") or control.get("name", "")
            if not str(result[name]).strip():
                raise ValueError("Consequence evidence is empty")
        if permission == "software.install":
            result["source"] = session.identity.display_name
            if result["cost"].strip().casefold() not in {"free", "$0.00", "0.00"}:
                raise PermissionError("Only explicitly free installations use this flow; purchase approval is separate")
            result["cost"] = "free"
        return result

    async def run(self, permission, target, bindings, expected):
        desktop = self.desktop
        if not desktop.sessions or not desktop.sessions.current:
            raise ValueError("Inspect the intended application first")
        session = desktop.sessions.sessions[desktop.sessions.current]
        before = await desktop.gateway.observe(session)
        session.observe(before)
        control = DesktopTargetResolver().resolve(before["controls"], target)
        if "invoke" not in control.get("actions", []):
            raise ValueError("Select a semantic invokable control")
        step = DesktopStep(session.key, "invoke", target, {}, expected, permission)
        if any(all(item.get(key) == value for key, value in expected.items()) for item in before["controls"]):
            raise ValueError("Expected completion state already exists; select evidence of this action's result")
        preview = ActionPreview.create(session.identity.id, permission, self.details(session, before["controls"], permission, bindings))
        await desktop.gateway.approval(session, "desktop.control_application", "Control the selected application",
                                      {"application": session.identity.display_name, "target": control["name"]})
        await desktop.gateway.approval(session, permission, "Review the exact consequential action", preview.details, always=True)
        after = await desktop.gateway.observe(session)
        current = ActionPreview.create(session.identity.id, permission, self.details(session, after["controls"], permission, bindings))
        current_control = DesktopTargetResolver().resolve(after["controls"], target)
        if current.fingerprint != preview.fingerprint or current_control["name"] != control["name"]:
            raise PermissionError("Action evidence changed after approval")
        session.observe(after)
        permit = secrets.token_hex(24)
        desktop.gateway.permits[permit] = desktop.gateway.fingerprint(session, step)
        await desktop.gateway.execute(session, step, permit, desktop.stop_event)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            desktop.gateway.check()
            observation = await desktop.gateway.observe(session)
            session.observe(observation)
            if len([item for item in observation["controls"] if all(item.get(key) == value for key, value in expected.items())]) == 1:
                desktop.observation = observation
                desktop.record.status = "completed"
                desktop.record.verification = "Consequential action postcondition observed"
                desktop.publish()
                return {"verified": True, "permission": permission}
            await asyncio.sleep(.1)
        raise TimeoutError("Action was requested but not verified; review before any retry")
