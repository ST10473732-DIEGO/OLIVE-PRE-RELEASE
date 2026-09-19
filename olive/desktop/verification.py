"""Bounded semantic postconditions, separate from action target selection."""

import re
from .target_resolver import normalized


def contains_destination(text, destination):
    return bool(re.search(r"(?<![\w@.+-])" + re.escape(normalized(destination)) +
                          r"(?![\w@.+-])", normalized(text)))


def within(control, ancestor_id, controls):
    parents = {c.get("runtime_id"): c.get("parent_id") for c in controls}
    current, seen = control.get("runtime_id"), set()
    for _ in range(32):
        if current == ancestor_id:
            return True
        if not current or current in seen:
            return False
        seen.add(current)
        current = parents.get(current)
    return False


def matches(control, expected):
    token = expected.get("name_token")
    if token is not None:
        if expected.get("control_type") != "Window" or control.get("control_type") != "Window":
            return False
        if not contains_destination(control.get("name", ""), token):
            return False
    return all(control.get(key) == value for key, value in expected.items() if key != "name_token")
