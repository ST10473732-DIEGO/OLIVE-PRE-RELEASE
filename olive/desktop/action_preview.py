"""Semantic consequence previews, independent of any application or widget."""

from dataclasses import dataclass
import hashlib
import json


REQUIRED_FIELDS = {
    "communication.send": ("destination", "body"),
    "software.install": ("application", "source", "publisher", "cost"),
    "software.purchase": ("item", "price", "account"),
    "application.delete": ("object",),
    "application.upload": ("destination", "files"),
    "application.submit": ("destination", "content"),
    "application.security_settings": ("setting", "old_value", "new_value"),
}


@dataclass(frozen=True)
class ActionPreview:
    application_id: str
    permission: str
    content_json: str

    @classmethod
    def create(cls, application_id, permission, details):
        if permission not in REQUIRED_FIELDS or not application_id:
            raise ValueError("Unknown consequential action")
        if not isinstance(details, dict) or any(key not in details for key in REQUIRED_FIELDS[permission]):
            raise ValueError("Consequential action preview is incomplete")
        content = json.dumps(details, sort_keys=True, ensure_ascii=False, allow_nan=False)
        if len(content) > 32768:
            raise ValueError("Action preview exceeds size limit")
        if permission == "software.install" and details["cost"] != "free":
            raise ValueError("A non-free or unknown-cost installation requires a separate purchase review")
        return cls(application_id, permission, content)

    @property
    def details(self):
        return json.loads(self.content_json)

    @property
    def fingerprint(self):
        return hashlib.sha256((self.application_id + "\n" + self.permission + "\n" + self.content_json).encode()).hexdigest()


def resolve_recipient(candidates):
    """Only an unambiguous explicit address is usable; display names are insufficient."""
    if len(candidates) != 1 or not candidates[0].get("address"):
        raise ValueError("Select the intended recipient and verify their address")
    return dict(candidates[0])
