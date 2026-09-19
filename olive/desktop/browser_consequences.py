"""Exact draft/file previews tied to current observed browser controls."""

import asyncio
import hashlib
import mimetypes
from pathlib import Path
import re

from .action_preview import ActionPreview


class BrowserConsequences:
    def __init__(self, controller):
        self.c = controller

    async def draft(self, fields):
        if not isinstance(fields, dict) or set(fields) != {"destination", "subject", "body", "send"}:
            raise ValueError("Select recipient, subject, message and Send controls")
        if len(set(fields.values())) != 4:
            raise ValueError("Draft controls must be distinct")
        provider = self.c.provider
        tabs = {provider.targets[value][0] for value in fields.values()}
        if len(tabs) != 1:
            raise ValueError("Draft controls must belong to the same tab")
        tab = next(iter(tabs))
        values = {key: await self.c.execute("field_value", target_id=value) for key, value in fields.items() if key != "send"}
        if not re.fullmatch(r"[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+", values["destination"]):
            raise ValueError("An unambiguous full recipient address must be visible in the selected field")
        if not values["body"].strip() or any(len(value) > 5000 for value in values.values()):
            raise ValueError("Draft content is empty or exceeds the review limit")
        await provider.target(fields["send"])
        return tab, {**values, "url": provider.pages[tab].url,
                     "attachments": await provider.attachment_names(tab)}

    async def send(self, fields, expected):
        provider, desktop = self.c.provider, self.c.desktop
        desktop.gateway.check()
        tab, details = await self.draft(fields)
        if not isinstance(expected, str) or not 1 <= len(expected.strip()) <= 300:
            raise ValueError("Specify the expected sent-state control")
        if any(signature["label"] == expected for signature in provider.target_signatures.values()):
            raise ValueError("The verification control is already present; choose evidence of a new sent state")
        preview = ActionPreview.create(self.c.session.identity.id, "communication.send", details)
        await desktop.gateway.approval(self.c.session, "desktop.control_application", "Control the reviewed browser draft",
                                      {"application": "Interactive browser", "url": details["url"]})
        await desktop.gateway.approval(self.c.session, preview.permission, "Send the exact reviewed message",
                                      preview.details, always=True)
        _, current = await self.draft(fields)
        if ActionPreview.create(self.c.session.identity.id, preview.permission, current).fingerprint != preview.fingerprint:
            raise PermissionError("Draft changed after approval; review it again")
        desktop.gateway.require_not_denied(self.c.session, "desktop.control_application")
        desktop.gateway.require_not_denied(self.c.session, preview.permission)
        window = await self.c.focus.prepare(provider.profile)
        provider.action_guard = lambda: self.c.focus.verify(window)
        result = await self.c.execute("act", target_id=fields["send"], action="click")
        self.c.focus.verify(window)
        if len([item for item in result["controls"] if item["name"] == expected]) != 1:
            raise ValueError("Send was requested, but a sent state was not verified. Do not resend without review.")
        result["verified"] = True
        desktop.s.agent_audit.record(task_id=self.c.session.task_id, tool="communication.send",
            requested_action="Reviewed browser communication", result_status="verified",
            permission_decision="allow", confirmation_result="approved")
        return result

    async def upload(self, target_id, path):
        controller, desktop = self.c, self.c.desktop
        tab, element = await controller.provider.target(target_id)
        if await element.get_attribute("type") != "file":
            raise ValueError("Select a file-upload control")
        source = Path(path).expanduser().resolve(strict=True)
        await desktop.gateway.approval(controller.session, "filesystem.read", "Read the selected attachment",
                                      {"path": str(source)}, always=True)
        def read():
            with source.open("rb") as stream:
                data = stream.read(10 * 1024 * 1024 + 1)
            if len(data) > 10 * 1024 * 1024:
                raise ValueError("Attachment exceeds the 10 MiB transfer limit")
            return data
        data = await asyncio.to_thread(read)
        digest = hashlib.sha256(data).hexdigest()
        details = {"destination": controller.provider.pages[tab].url,
                   "files": [{"name": source.name, "size": len(data), "sha256": digest}]}
        preview = ActionPreview.create(controller.session.identity.id, "application.upload", details)
        await desktop.gateway.approval(controller.session, preview.permission, "Upload the selected file to this website",
                                      preview.details, always=True)
        desktop.gateway.require_not_denied(controller.session, "filesystem.read", str(source))
        desktop.gateway.require_not_denied(controller.session, preview.permission)
        if hashlib.sha256(await asyncio.to_thread(read)).hexdigest() != digest:
            raise PermissionError("Attachment changed after approval")
        window = await controller.focus.prepare(controller.provider.profile)
        controller.provider.action_guard = lambda: controller.focus.verify(window)
        result = await controller.execute("upload", target_id=target_id, name=source.name,
            mime_type=mimetypes.guess_type(source.name)[0] or "application/octet-stream", data=data)
        controller.focus.verify(window)
        return result
