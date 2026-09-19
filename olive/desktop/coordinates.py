"""Explicit vision -> capture pixels -> physical client/screen transforms."""
import math


def capture_bounds(bounds, coordinate_space, width, height):
    if type(width) is not int or type(height) is not int or min(width, height) <= 0:
        raise ValueError("Invalid capture dimensions")
    if set(bounds) != {"left", "top", "right", "bottom"} or any(type(v) is not int for v in bounds.values()):
        raise ValueError("Invalid target rectangle")
    if coordinate_space not in {"capture_pixels", "normalized_0_1000"}:
        raise ValueError("Unsupported visual coordinate space")
    limit_x, limit_y = (width, height) if coordinate_space == "capture_pixels" else (1000, 1000)
    if not (0 <= bounds["left"] < bounds["right"] <= limit_x and 0 <= bounds["top"] < bounds["bottom"] <= limit_y):
        raise ValueError("Target lies outside captured region")
    return {key: (math.floor if key in {"left", "top"} else math.ceil)(value *
            (width / limit_x if key in {"left", "right"} else height / limit_y)) for key, value in bounds.items()}


def screen_point(capture, bounds):
    bounds = capture_bounds(bounds, "capture_pixels", capture["width"], capture["height"])
    client = capture.get("client_bounds")
    if not client or client["right"] <= client["left"] or client["bottom"] <= client["top"]:
        raise ValueError("Visual target has no valid capture coordinate mapping")
    # client_bounds already uses physical screen pixels, including negative monitor
    # origins. Applying DPI again here would double-scale the target.
    return tuple(round(client[start] + (bounds[start] + bounds[end]) / 2 / capture[dimension] *
                       (client[end] - client[start])) for start, end, dimension in
                 (("left", "right", "width"), ("top", "bottom", "height")))
