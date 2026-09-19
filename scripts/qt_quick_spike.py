"""LIVE LOCAL: isolated Qt Quick/Widgets integration and retention spike."""
import argparse
import json
from pathlib import Path
import sys
import time
import tempfile

import psutil
from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget, QPlainTextEdit, QDockWidget
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
from PySide6.QtQuickWidgets import QQuickWidget

parser = argparse.ArgumentParser()
parser.add_argument("--backend", choices=["default", "opengl"], default="opengl")
parser.add_argument("--output", default=".qt-spike-350")
parser.add_argument("--webengine", action="store_true")
args = parser.parse_args()
output = Path(args.output); output.mkdir(parents=True, exist_ok=True)
if args.backend == "opengl":
    QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
app = QApplication([])
process = psutil.Process()
before = process.memory_info().rss
started = time.perf_counter()
window = QMainWindow(); window.resize(1100, 760)
stack = QStackedWidget(); window.setCentralWidget(stack)
native = QMainWindow(); editor = QPlainTextEdit("temporary unsaved buffer\nprint('OLIVE')")
native.setCentralWidget(editor)
dock = QDockWidget("Output", native); dock.setWidget(QPlainTextEdit("Retained QWidget dock"))
native.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
stack.addWidget(native)
widget_ms = (time.perf_counter() - started) * 1000
source = '''import QtQuick
import QtQuick.Controls
Rectangle {
 color: "#090d14"
 Text { anchors.centerIn: parent; text: "OLIVE Qt integration spike"; color: "#edf3fc"; font.pixelSize: 30 }
 TextField { anchors.horizontalCenter: parent.horizontalCenter; y: parent.height * 0.65; placeholderText: "Keyboard focus remains usable" }
}'''
temporary = tempfile.TemporaryDirectory(prefix="olive-quick-spike-")
qml = Path(temporary.name) / "Spike.qml"; qml.write_text(source, encoding="utf-8")
quick_started = time.perf_counter()
quick = QQuickWidget(); quick.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
quick.setSource(QUrl.fromLocalFile(str(qml)))
stack.addWidget(quick); stack.setCurrentWidget(quick)
quick_ms = (time.perf_counter() - quick_started) * 1000
window.show()
result = {"backend_requested": args.backend, "widget_construction_ms": round(widget_ms, 2),
          "quick_construction_ms": round(quick_ms, 2), "checks": {}}
web_loaded = False
if args.webengine:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    preview = QWebEngineView()
    def loaded(ok):
        global web_loaded
        web_loaded = ok
    preview.loadFinished.connect(loaded)
    stack.addWidget(preview); stack.setCurrentWidget(preview)
    preview.setHtml("<html><body><h1>OLIVE isolated local preview</h1></body></html>")

def check():
    result["checks"]["qml_loaded"] = quick.status() == QQuickWidget.Status.Ready
    if args.webengine:
        result["checks"]["webengine_loaded"] = web_loaded
    result["qml_errors"] = [e.toString() for e in quick.errors()]
    result["backend"] = str(quick.quickWindow().rendererInterface().graphicsApi())
    image = quick.grabFramebuffer()
    result["checks"]["rendered_frame"] = not image.isNull()
    image.save(str(output / (args.backend + "-quick.png")))
    cursor = editor.textCursor(); cursor.setPosition(8); editor.setTextCursor(cursor)
    for _ in range(20):
        stack.setCurrentWidget(native); stack.setCurrentWidget(quick)
    stack.setCurrentWidget(native)
    result["checks"]["buffer_and_cursor_retained"] = editor.toPlainText().startswith("temporary unsaved") and editor.textCursor().position() == 8
    result["checks"]["native_dock_retained"] = dock.parent() == native and dock.isVisible()
    result["checks"]["single_top_level"] = sum(w.isVisible() and isinstance(w, QMainWindow) for w in app.topLevelWidgets()) == 1
    result["rss_delta_mib"] = round((process.memory_info().rss - before) / 1024**2, 2)
    (output / (args.backend + ".json")).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)
    window.close(); app.quit()

QTimer.singleShot(2500 if args.webengine else 500, check)
app.exec()
temporary.cleanup()
raise SystemExit(0 if all(result["checks"].values()) else 1)
