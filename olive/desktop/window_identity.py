"""Normalize an OS-hosted application without confusing its frame with its process."""


def merge_hosted_window(frame, content):
    if frame.get("window_class") != "ApplicationFrameWindow" or not content.get("package_identity"):
        raise ValueError("A packaged application and its Windows frame are required")
    return {**frame, "host_pid": frame["pid"], "content_hwnd": content["hwnd"],
            **{key: content[key] for key in ("pid", "application", "executable", "package_identity")}}


def foreground_matches(window, hwnd, process_id):
    return window["hwnd"] == hwnd and window.get("host_pid", window["pid"]) == process_id
