"""Validated conservative desktop configuration."""

DEFAULTS = {"enabled": False, "screen_observation": False, "vision_fallback": False,
            "uia": True, "keyboard_policy": "deny", "mouse_policy": "deny",
            "screenshot_retention": 10, "unknown_app_policy": "ask",
            "emergency_shortcut": "Ctrl+Alt+Escape", "user_takeover": "pause"}


def validate(value=None):
    if value is None:
        value = {}
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValueError("Unknown desktop setting")
    result = {**DEFAULTS, **value}
    for key in ("enabled", "screen_observation", "vision_fallback", "uia"):
        if type(result[key]) is not bool:
            raise ValueError("Desktop switches must be boolean")
    for key in ("keyboard_policy", "mouse_policy", "unknown_app_policy"):
        if result[key] not in ("deny", "ask", "allow"):
            raise ValueError("Invalid input policy")
    if type(result["screenshot_retention"]) is not int or not 1 <= result["screenshot_retention"] <= 100:
        raise ValueError("Screenshot retention must be 1–100")
    if result["user_takeover"] != "pause" or result["emergency_shortcut"] not in ("Ctrl+Alt+Escape", ""):
        raise ValueError("Unsupported takeover or emergency shortcut setting")
    return result
