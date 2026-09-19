from __future__ import annotations

from dataclasses import dataclass,field


@dataclass(frozen=True,slots=True)
class ExternalMessagePreview:
    application:str
    recipient:str
    message:str
    attachments:tuple[str,...]=field(default_factory=tuple)
    permission:str="communication.send"

    def __post_init__(self):
        if not self.application.strip() or not self.recipient.strip() or not self.message.strip():
            raise ValueError("Application, recipient, and exact message are required")
