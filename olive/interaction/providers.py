"""Resolve capability providers after semantic interpretation, using saved preferences."""

from ..desktop.application_discovery import normalized


async def media_session(services, context, application=""):
    sessions = await services.desktop.media_sessions()
    name = application or getattr(context, "media_application", None)
    aliases = getattr(services, "settings", {}).get("application_aliases", {})
    if (application and application.casefold() in aliases) or (not name and "music" in aliases):
        await services.desktop.discover_applications()
        app = services.desktop.discovery.resolve(application or "music")
        name = app.display_name
    def key(value):
        return normalized(value).replace(" ", "")
    matches = [item for item in sessions if not name or key(name) in key(item["application_id"])]
    if len(matches) != 1:
        raise ValueError("Which music application should I use?")
    return matches[0]


async def browser_channel(services, context, application=""):
    name = application or context.browser_application or "browser"
    aliases = getattr(services, "settings", {}).get("application_aliases", {})
    if name.casefold() in aliases:
        await services.desktop.discover_applications()
        name = services.desktop.discovery.resolve(name).display_name
    channels = {"browser": "chrome", "chrome": "chrome", "google chrome": "chrome",
                "edge": "msedge", "microsoft edge": "msedge", "msedge": "msedge"}
    channel = channels.get(normalized(name))
    if not channel:
        raise ValueError("I can't use that browser for this web workflow yet. Choose Chrome or Edge.")
    return channel, "Edge" if channel == "msedge" else "Chrome"
