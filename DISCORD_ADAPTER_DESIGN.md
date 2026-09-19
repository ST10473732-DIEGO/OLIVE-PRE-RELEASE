# OLIVE Discord adapter design

OLIVE will use Discord's supported bot/application APIs only. It will not automate a normal user account as a self-bot.

The future adapter may expose server/channel listing, permitted channel reading and search, replies, and message sending. Discord permissions remain authoritative. Every send operation uses `communication.send` and presents the application, server/channel or recipient, exact message, and attachments for Send/Edit/Cancel confirmation.

Opening or navigating the visible Discord desktop application is a separate future `DesktopControlService` capability. Application content is untrusted observation and never authorizes an action.


OLIVE was formerly named DMDO. See [the rebrand compatibility map](docs/OLIVE_REBRAND.md) for legacy profile, import, launcher and security identities. Historical evidence retains its original name.
