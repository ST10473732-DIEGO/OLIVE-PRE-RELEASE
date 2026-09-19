"""Window-scoped snapshots and freshness checks; never a background recorder."""

import base64
import io
import time
import uuid
from pathlib import Path

from .windows_observation import verify_identity, physical_coordinates


def capture_window(target):
    from PIL import ImageGrab
    before = verify_identity(target)
    if before["minimized"] or not before["visible"]:
        raise ValueError("Restore the target window before capturing it")
    bounds = before["bounds"]
    if (bounds["right"] - bounds["left"]) * (bounds["bottom"] - bounds["top"]) > 8_000_000:
        raise ValueError("Window exceeds capture pixel limit")
    with physical_coordinates():
        import win32gui
        client = win32gui.GetClientRect(before["hwnd"])
        origin = win32gui.ClientToScreen(before["hwnd"], (0, 0))
        end = win32gui.ClientToScreen(before["hwnd"], (client[2], client[3]))
        picture = ImageGrab.grab(window=before["hwnd"])
    after = verify_identity(target)
    if before["bounds"] != after["bounds"] or before["dpi"] != after["dpi"]:
        raise ValueError("Window moved during capture; retry")
    picture.thumbnail((1600, 1200))
    output = io.BytesIO()
    picture.save(output, format="PNG")
    if len(output.getvalue()) > 4 * 1024 * 1024:
        raise ValueError("Capture exceeds artifact size limit")
    return {"window": before, "width": picture.width, "height": picture.height,
            "client_bounds": dict(zip(("left", "top", "right", "bottom"), (*origin, *end))),
            "image": base64.b64encode(output.getvalue()).decode("ascii")}


class ScreenshotStore:
    def __init__(self, root):
        self.root = Path(root)
        self.records = {}

    def add(self, task_id, capture, retention=10):
        task = str(uuid.UUID(task_id))
        directory = self.root / task
        directory.mkdir(parents=True, exist_ok=True)
        capture_id = str(uuid.uuid4())
        path = directory / (capture_id + ".png")
        path.write_bytes(base64.b64decode(capture["image"], validate=True))
        record = {key: value for key, value in capture.items() if key != "image"}
        record.update(id=capture_id, task_id=task, path=str(path), monotonic=time.monotonic())
        self.records[capture_id] = record
        for old in list(self.records)[:-retention]:
            Path(self.records.pop(old)["path"]).unlink(missing_ok=True)
        self.cleanup(retention)
        return record

    def cleanup(self, retention):
        root = self.root.resolve()
        owned = []
        for path in self.root.glob("*/*.png"):
            if path.is_symlink() or path.parent.is_symlink() or not path.resolve().is_relative_to(root):
                continue
            try:
                uuid.UUID(path.parent.name)
                uuid.UUID(path.stem)
            except ValueError:
                continue
            owned.append(path)
        for path in sorted(owned, key=lambda item: item.stat().st_mtime)[:-retention]:
            path.unlink(missing_ok=True)

    def validate_target(self, capture_id, current_window, bounds, max_age=15):
        record = self.records[capture_id]
        if time.monotonic() - record["monotonic"] > max_age:
            raise ValueError("Screenshot is stale")
        if any(current_window.get(key) != record["window"].get(key) for key in ("hwnd", "pid", "bounds", "dpi")):
            raise ValueError("Screenshot no longer matches the target window")
        if set(bounds) != {"left", "top", "right", "bottom"} or any(type(value) is not int for value in bounds.values()):
            raise ValueError("Invalid visual target bounds")
        if not (0 <= bounds["left"] < bounds["right"] <= record["width"] and
                0 <= bounds["top"] < bounds["bottom"] <= record["height"]):
            raise ValueError("Visual target is outside the authorized screenshot")
        return record
