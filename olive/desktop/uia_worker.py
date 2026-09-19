"""Short-lived COM MTA worker. JSON observations leave the process; COM objects never do."""

import json
import sys
import time
sys.coinit_flags = 0

from .windows_observation import verify_identity
from .target_resolver import DesktopTargetResolver
from .emergency_stop import check_worker_stop
from .privacy import secret_field


def editor_value(wrapper):
    """Read accessible editor content; formatting-only placeholders are empty."""
    import unicodedata
    from comtypes import COMError
    from pywinauto.uia_defines import NoPatternInterfaceError
    try:
        value = wrapper.iface_value.CurrentValue
        value = "" if value is None else str(value)[:5001]
    except (NoPatternInterfaceError, COMError):
        try:
            value = str(wrapper.iface_text.DocumentRange.GetText(5001))
        except (NoPatternInterfaceError, COMError):
            value = ""
    return value if any(not ch.isspace() and unicodedata.category(ch) != "Cf" for ch in value) else ""


def hierarchy(root, limit=300, depth_limit=16):
    from comtypes import COMError
    from pywinauto.uia_defines import NoPatternInterfaceError
    queue, values, wrappers = [(root, "", 0)], [], {}
    deadline = time.monotonic() + 4
    truncated = False
    while queue and len(values) < limit and time.monotonic() < deadline:
        wrapper, parent, depth = queue.pop(0)
        info = wrapper.element_info
        runtime_id = ".".join(map(str, info.runtime_id))
        rect = wrapper.rectangle()
        password = secret_field(info.name, password=bool(info.element.CurrentIsPassword))
        value = ""
        if info.control_type in {"Edit", "Document"} and not password:
            value = editor_value(wrapper)
        item = {"runtime_id": runtime_id, "parent_id": parent, "automation_id": info.automation_id,
                "framework_id": info.framework_id, "class_name": info.class_name,
                "name": "[protected]" if password else info.name[:500], "control_type": info.control_type,
                "enabled": wrapper.is_enabled(), "visible": wrapper.is_visible(), "password": password,
                "focused": wrapper.has_keyboard_focus(), "value": value,
                "bounds": {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom}}
        patterns = {"iface_invoke": "invoke", "iface_selection_item": "select", "iface_expand_collapse": "expand",
                    "iface_value": "set_text", "iface_scroll": "scroll", "iface_toggle": "toggle"}
        item["actions"] = []
        if not password:
            for pattern, operation in patterns.items():
                try:
                    getattr(wrapper, pattern)
                    item["actions"].append(operation)
                except (NoPatternInterfaceError, COMError):
                    continue
        if "select" in item["actions"]:
            item["selected"] = bool(wrapper.iface_selection_item.CurrentIsSelected)
        if "toggle" in item["actions"]:
            item["checked"] = int(wrapper.iface_toggle.CurrentToggleState)
        values.append(item)
        wrappers[runtime_id] = wrapper
        children = wrapper.children()
        if depth < depth_limit:
            remaining = max(0, limit - len(values) - len(queue))
            truncated = truncated or len(children) > remaining
            queue.extend((child, runtime_id, depth + 1) for child in children[:remaining])
        else:
            truncated = truncated or bool(children)
    return values, wrappers, truncated or bool(queue)


def run(request):
    from pywinauto import Desktop
    check_worker_stop(request.get("stop_name"))
    action = request["action"]
    if action == "verify_folder":
        from pathlib import Path
        from urllib.parse import unquote
        import win32com.client
        from .windows_observation import inspect_window
        wanted = unquote(Path(request["path"]).resolve(strict=True).as_uri()).rstrip("/").casefold()
        shell = win32com.client.Dispatch("Shell.Application")
        matches = []
        for window in shell.Windows():
            if unquote(str(window.LocationURL)).rstrip("/").casefold() == wanted:
                matches.append(inspect_window(int(window.HWND)))
        return {"verified": bool(matches), "windows": matches}
    if action == "capture":
        from .capture import capture_window
        return capture_window(request["window"])
    if action == "visual_click":
        import base64
        import hashlib
        from .capture import capture_window
        from .windows_input import click_window
        capture = capture_window(request["window"])
        if hashlib.sha256(base64.b64decode(capture["image"])).hexdigest() != request["image_hash"]:
            raise PermissionError("Visual target changed before input")
        click_window(request["window"], request["point"], request["client_bounds"], request["stop_name"])
        return {"acted": True, "verified": False}
    if action not in {"observe", "invoke", "select", "expand", "collapse", "set_text", "focus", "scroll", "activate", "toggle", "search", "submit_message"}:
        raise ValueError("Unknown UI Automation action")
    window = verify_identity(request["window"], foreground=action not in {"observe", "activate"})
    if action == "activate":
        import win32gui
        import win32con
        import win32process
        if window["foreground"]:
            return {"window": window, "acted": False, "verified": True}
        expected = request.get("expected_foreground")
        if expected:
            foreground = win32gui.GetForegroundWindow()
            if foreground != expected["hwnd"] or win32process.GetWindowThreadProcessId(foreground)[1] != expected["pid"]:
                raise PermissionError("Focus changed before the approved application switch")
        if window["minimized"]:
            win32gui.ShowWindow(window["hwnd"], win32con.SW_RESTORE)
        check_worker_stop(request.get("stop_name"))
        win32gui.SetForegroundWindow(window["hwnd"])
        return {"window": verify_identity(request["window"], foreground=True), "acted": True}
    root = Desktop(backend="uia").window(handle=window["hwnd"]).wrapper_object()
    limit, depth = request.get("control_limit", 300), request.get("depth_limit", 16)
    if type(limit) is not int or not 1 <= limit <= 1200 or type(depth) is not int or not 1 <= depth <= 24:
        raise ValueError("Accessibility observation exceeds its bounded budget")
    controls, wrappers, truncated = hierarchy(root, limit=limit if action == "observe" else 300,
                                              depth_limit=depth if action == "observe" else 16)
    if action == "observe":
        return {"window": window, "controls": controls, "truncated": truncated, "untrusted_content": True}
    target = DesktopTargetResolver().resolve(controls, request.get("target", {}))
    wrapper = wrappers[target["runtime_id"]]
    if target["password"]:
        raise PermissionError("Protected controls require direct user input")
    verify_identity(request["window"], foreground=True)
    check_worker_stop(request.get("stop_name"))
    if action == "submit_message":
        text = request.get("text")
        if (target["control_type"] != "Edit" or not isinstance(text, str) or
                not 1 <= len(text) <= 4000 or target.get("value") != text):
            raise PermissionError("The reviewed message editor changed before submission")
        wrapper.set_focus()
        if editor_value(wrapper) != text:
            raise PermissionError("The message changed after focusing its editor")
        from .message_submission import destination_text
        fresh, _, _ = hierarchy(root)
        if destination_text(fresh, request.get("destination")) != request.get("destination_text"):
            raise PermissionError("The destination changed before the reviewed submission")
        if editor_value(wrapper) != text:
            raise PermissionError("The message changed before the reviewed submission")
        from .windows_input import submit_reviewed_message
        submit_reviewed_message(request["window"], wrapper, request["stop_name"])
    elif action in {"set_text", "search"}:
        if target["control_type"] not in {"Edit", "Document"}:
            raise ValueError("Target is not a text control")
        text = request.get("text", "")
        if not isinstance(text, str) or len(text) > 5000:
            raise ValueError("Text exceeds input limit")
        if "expected_previous" in request and editor_value(wrapper) != request["expected_previous"]:
            raise PermissionError("The field changed after text-entry review")
        from .privacy import search_field
        if action == "search" and (not search_field(target) or not 1 <= len(text) <= 200):
            raise PermissionError("Only a bounded query in an accessible search field can submit search")
        # ValuePattern is target-specific; it cannot redirect typing to another application.
        from pywinauto.uia_defines import NoPatternInterfaceError
        if action == "set_text" and target.get("framework_id") == "Chrome" and target["control_type"] == "Edit":
            from .windows_input import replace_empty_or_identical_editor
            if request.get("pointer_focus"):
                from .windows_input import focus_editor_pointer
                focus_editor_pointer(request["window"], wrapper, request["stop_name"])
            wrapper.set_focus()
            previous = editor_value(wrapper)
            if previous != target.get("value", ""):
                raise PermissionError("The editor changed before text entry")
            replace_empty_or_identical_editor(request["window"], wrapper, text, previous, request["stop_name"], editor_value,
                                             expected_previous=request.get("expected_previous"))
        else:
            try:
                wrapper.iface_value.SetValue(text)
            except NoPatternInterfaceError:
                if target.get("value"):
                    raise PermissionError("Raw text fallback requires an empty editor; clear it manually first")
                from .windows_input import type_unicode
                wrapper.set_focus()
                type_unicode(request["window"], wrapper, text, request["stop_name"])
        if action == "search":
            if str(wrapper.iface_value.CurrentValue) != text:
                raise ValueError("Search field value was not verified")
            wrapper.set_focus()
            from .windows_input import submit_search
            submit_search(request["window"], wrapper, request["stop_name"])
    elif action == "invoke":
        wrapper.iface_invoke.Invoke()
    elif action == "select":
        wrapper.iface_selection_item.Select()
    elif action == "expand":
        wrapper.iface_expand_collapse.Expand()
    elif action == "collapse":
        wrapper.iface_expand_collapse.Collapse()
    elif action == "focus":
        wrapper.set_focus()
    elif action == "toggle":
        wrapper.iface_toggle.Toggle()
    else:
        direction = request.get("direction", "down")
        if direction not in {"up", "down"}:
            raise ValueError("Invalid scroll direction")
        wrapper.iface_scroll.Scroll(2, 1 if direction == "up" else 3)
    verify_identity(request["window"], foreground=True)
    return {"acted": True, "control_id": target["runtime_id"], "action": action}


if __name__ == "__main__":
    try:
        data = sys.stdin.buffer.read(65537)
        if len(data) > 65536:
            raise ValueError("Oversized UIA request")
        result = {"ok": True, "value": run(json.loads(data))}
    except Exception as error:
        # Never include an exception's potentially sensitive control/text payload.
        safe_messages = {"Focus changed before the approved application switch",
                         "Window identity changed; review the target again",
                         "Target lost foreground focus; input stopped",
                         "Protected controls require direct user input",
                         "The reviewed editor did not clear; text entry stopped",
                         "A keyboard modifier is held; input stopped for user takeover",
                         "The reviewed editor lost focus",
                         "Windows rejected replacement in the reviewed editor",
                         "Target is not a text control", "Text exceeds input limit",
                         "NULL COM pointer access", "Fallback accepts bounded printable text only"}
        message = str(error) if str(error) in safe_messages else "Windows accessibility operation failed; refresh the target or use an authorized fallback"
        result = {"ok": False, "error": type(error).__name__, "message": message,
                  "code": getattr(error, "hresult", None)}
    sys.stdout.write(json.dumps(result))
