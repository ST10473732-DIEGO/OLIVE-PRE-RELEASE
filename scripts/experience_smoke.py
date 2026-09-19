"""Live-local Midnight shell checks in an isolated profile, with no model/network work."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import subprocess
import shutil
process_started = time.perf_counter()

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
parser = argparse.ArgumentParser()
parser.add_argument("--output", default=".experience-350")
parser.add_argument("--record", action="store_true")
parser.add_argument("--width", type=int, default=1366)
parser.add_argument("--height", type=int, default=768)
args = parser.parse_args()
output = Path(args.output).resolve(); output.mkdir(parents=True, exist_ok=True)
profile = tempfile.TemporaryDirectory(prefix="olive-midnight-")
os.environ["OLIVE_DATA_DIR"] = str(Path(profile.name) / "data")
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel
from olive.application.service_container import ServiceContainer
from olive.ui_qt.application import OliveApplication


class LocalServices(ServiceContainer):
    async def initialize(self):
        self.model_infos = []
        self.ollama_state = "Unavailable (isolated offline test)"
        self.publish("status", self.data.status())

    async def dispatch(self, operation, arguments):
        if operation == "fixture.populate":
            # Test-only entry, never registered in the production service container.
            chat = self.chats[self.current_chat_id]
            chat.title = "Weekend trail companion · fixture"
            chat.add_message("user", "Help me plan a small offline trail companion for a weekend walk.")
            chat.add_message("assistant", "Start with a small, useful first version:\n\n1. Save a route locally.\n2. Show the next waypoint.\n3. Keep a short trip journal.\n\n**Keep location sharing off by default.** We can build the route reader first, then test it using synthetic coordinates.")
            chat.add_message("user", "What should the route reader return?")
            chat.add_message("assistant", "A clear, validated record for each waypoint:\n\n```python\ndef waypoint(name, latitude, longitude):\n    return {\n        'name': name,\n        'latitude': latitude,\n        'longitude': longitude,\n    }\n```\n\nValidate the coordinate ranges before saving.")
            self.save_chats()
            workspace = Path(profile.name) / "workspace"; workspace.mkdir(exist_ok=True)
            (workspace / "route.py").write_text("\"\"\"Synthetic trail companion fixture.\"\"\"\n\ndef waypoint(name, latitude, longitude):\n    if not -90 <= latitude <= 90:\n        raise ValueError('Latitude is outside its valid range')\n    return dict(name=name, latitude=latitude, longitude=longitude)\n\nprint(waypoint('Start', -26.0, 28.0))\n", encoding="utf-8")
            (workspace / "main.py").write_text("from route import waypoint\nprint('Fixture run completed.')\n", encoding="utf-8")
            w = self.data.create_workspace("Trail companion · fixture", str(workspace))
            return {"chat":self.chat.get(), "workspace":w}
        return await super().dispatch(operation, arguments)


started = time.perf_counter()
application = OliveApplication(factory=lambda notify, confirm: LocalServices(notify, confirm, Path(profile.name) / "data", migrate=False), presentation="midnight")
manager = application.manager
manager.main.resize(args.width, args.height)
results = []
def approve_fixture_read(request):
    dialog = manager.dialogs.get(request.id)
    scope = Path(request.arguments.get("workspace", ".")).resolve()
    allowed = request.tool_name in {"studio.open", "studio.tree", "studio.run"} and scope == (Path(profile.name)/"workspace").resolve()
    if dialog:
        QTimer.singleShot(0, dialog.approve if allowed else dialog.reject)
manager.bridge.confirmation.connect(approve_fixture_read)
fixture = {}
frames = []
record_timer = QTimer(); record_timer.setInterval(80)
if args.record:
    (output / "frames").mkdir(exist_ok=True)
    def frame():
        index = len(frames)
        manager.main.grab().save(str(output / "frames" / f"{index:05d}.png"))
        frames.append(time.perf_counter())
    record_timer.timeout.connect(frame); record_timer.start()
banner = QLabel("ISOLATED DEMONSTRATION · synthetic data · no external actions")
banner.setObjectName("eyebrow"); banner.setContentsMargins(24, 6, 24, 6)
manager.main.centralWidget().layout().insertWidget(0, banner)


def check(name, condition):
    results.append({"name": name, "pass": bool(condition)})
    print(("PASS " if condition else "FAIL ") + name, flush=True)


def capture(name):
    manager.main.grab().save(str(output / f"{name}.png"))


def welcome():
    check("Welcome starts visible", manager.experience.welcome)
    check("Entry available without a model", manager.experience.entryAllowed)
    capture("welcome")
    manager.workspace("home").surface.setFocus()
    QTest.keyClick(manager.workspace("home").surface, Qt.Key.Key_Return)
    check("Keyboard Enter activates Welcome", not manager.experience.welcome)
    QTimer.singleShot(450, home)


def home():
    check("Enter shows Home", not manager.experience.welcome and manager.navigation.current == "home")
    capture("home-empty")
    manager.experience.showSpaces()
    QTimer.singleShot(200, spaces)


def spaces():
    capture("all-spaces")
    check("All shipped features discoverable", manager.experience.spaces.rowCount() == len(manager.registry.list()))
    manager.experience.navigate("chat")
    QTimer.singleShot(300, chat_empty)


def chat_empty():
    capture("chat-empty")
    def populated(value, error):
        check("Synthetic fixture persisted through real repositories", value is not None and not error)
        if value: fixture.update(value)
        manager.experience.navigate("home")
        manager.experience.refresh()
        QTimer.singleShot(350, populated_home)
    manager.bridge.call("fixture.populate", populated)


def populated_home():
    capture("home-populated-fixture")
    manager.experience.navigate("chat")
    manager.workspace("chat").select_chat(fixture["chat"]["id"])
    QTimer.singleShot(350, populated_chat)


def populated_chat():
    capture("chat-populated-fixture")
    chat = manager.workspace("chat")
    chat.composer.setPlainText("Keep this unsent draft while I work in Studio.")
    manager.experience.navigate("studio")
    page = manager.workspace("studio")
    page.workspace_id = fixture["workspace"]["id"]
    page.refresh()
    page.open_file("route.py", workspace_id=page.workspace_id)
    QTimer.singleShot(500, studio)


def studio():
    original = manager.workspace("studio")
    document = original.active_document()
    check("Studio opens a real authorised fixture file", document is not None)
    if document:
        editor = document["editor"]
        editor.insertPlainText("# Unsent buffer retained across navigation\n")
        fixture["editor_text"] = editor.get_text()
        fixture["cursor"] = editor.textCursor().position()
    capture("studio-code-fixture")
    manager.experience.navigate("home")
    manager.experience.navigate("studio")
    check("Studio instance retained", original is manager.workspace("studio"))
    if document:
        check("Unsaved Studio buffer and cursor retained", editor.get_text()==fixture["editor_text"] and editor.textCursor().position()==fixture["cursor"] and editor.document().isModified())
        # Do not save this test edit. Only a disposable fixture buffer is reset.
        editor.set_text(document["saved"])
    original.run()
    QTimer.singleShot(650, studio_output)


def studio_output():
    page = manager.workspace("studio")
    check("Studio Run displays actual fixture output", "Fixture run completed." in page.output.toPlainText())
    capture("studio-code-output-fixture")
    manager.experience.navigate("chat")
    check("Chat composer retained across workspaces", manager.workspace("chat").composer.toPlainText()=="Keep this unsent draft while I work in Studio.")
    manager.experience.navigate("home")
    check("Returning Home does not reopen Welcome", not manager.experience.welcome)
    manager.experience.showGallery()
    QTimer.singleShot(200, finish)


def finish():
    capture("gallery")
    manager.experience.setReducedMotion(True)
    manager.experience.setLightTheme(True)
    manager.experience.navigate("home")
    QTimer.singleShot(200, light)


def light():
    capture("home-light-fixture")
    check("Light theme and Reduced Motion applied", manager.experience.lightTheme and manager.experience.reducedMotion)
    manager.main.resize(820, 680)
    QTimer.singleShot(200, narrow)


def narrow():
    capture("home-narrow-fixture")
    navigation_ms = []
    for _ in range(10):
        before = time.perf_counter()
        manager.experience.navigate("chat"); manager.experience.navigate("home")
        navigation_ms.append((time.perf_counter()-before)*1000/2)
    check("Rapid navigation retains cached pages", len(manager.windows)==3)
    from olive.ui_qt.experience.surface import QuickSurface
    surfaces = manager.main.findChildren(QuickSurface)
    check("All QML surfaces loaded without errors", all(s.rootObject() is not None and not s.errors for s in surfaces))
    check("Single primary OLIVE window", sum(w.isVisible() and w.isWindow() for w in QApplication.topLevelWidgets()) == 1)
    record_timer.stop()
    import psutil
    process = psutil.Process()
    surface = manager.workspace("home").surface
    fixture["performance"] = {"construction_ms":application.startup_ms,
        "first_home_surface_paint_ms_after_imports":round((surface.first_paint_at-started)*1000,1) if surface.first_paint_at else None,
        "first_home_surface_paint_ms_including_qt_imports":round((surface.first_paint_at-process_started)*1000,1) if surface.first_paint_at else None,
        "cached_navigation_callback_mean_ms":round(sum(navigation_ms)/len(navigation_ms),2),
        "rss_mib":round(process.memory_info().rss/1024**2,1),
        "recording_enabled":args.record, "device_pixel_ratio":manager.main.devicePixelRatioF(),
        "gpu_vram":"NOT MEASURED", "display_frame_rate":"NOT MEASURED"}
    manager.main.hide()
    check("Hidden window disables Core animation", not manager.experience.windowActive)
    QTimer.singleShot(150, begin_idle)


def begin_idle():
    import psutil
    fixture["idle_cpu"] = sum(psutil.Process().cpu_times()[:2])
    fixture["idle_start"] = time.perf_counter()
    QTimer.singleShot(1200, complete)


def complete():
    import psutil
    fixture["performance"]["hidden_idle_cpu_one_core_percent"] = round(100*(sum(psutil.Process().cpu_times()[:2])-fixture["idle_cpu"])/(time.perf_counter()-fixture["idle_start"]),2)
    (output / "shell-results.json").write_text(json.dumps({"classification":"LIVE LOCAL; offline services; synthetic fixture; authorised local file read and harmless program run; no model or external communication",
        "performance":fixture["performance"],"checks":results}, indent=2))
    manager.exit()


QTimer.singleShot(1200, welcome)
QTimer.singleShot(20000, manager.exit)
application.run()
if args.record and frames and shutil.which("ffmpeg"):
    manifest = output / "frames" / "recording.txt"
    lines = []
    for i, stamp in enumerate(frames):
        lines.extend([f"file '{i:05d}.png'", f"duration {frames[i+1]-stamp if i+1<len(frames) else 0.08:.6f}"])
    lines.append(f"file '{len(frames)-1:05d}.png'")
    manifest.write_text("\n".join(lines), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(manifest),
        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-pix_fmt", "yuv420p", str(output / "m1-interaction.mp4")], check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
sys.exit(0 if results and all(r["pass"] for r in results) else 1)
