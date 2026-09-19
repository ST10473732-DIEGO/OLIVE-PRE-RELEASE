"""Desktop Control layout; runtime and permission logic stay in controllers."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QSplitter, QTabWidget,
    QCheckBox, QComboBox, QLineEdit, QLabel, QTreeWidget, QPushButton, QToolBar, QScrollArea)


def button(layout, text, callback):
    control = QPushButton(text)
    control.clicked.connect(callback)
    layout.addWidget(control)
    return control


def panel(tabs, title):
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setSpacing(10)
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(content)
    tabs.addTab(area, title)
    return layout


def build(window):
    w = window
    layout = w.page("Desktop Control", "Work across applications, with visible actions and verified results.")
    task = QHBoxLayout()
    w.objective = QLineEdit()
    w.objective.setPlaceholderText("What would you like OLIVE to do?")
    w.objective.setAccessibleName("Desktop task objective")
    task.addWidget(w.objective, 1)
    button(task, "Run objective", lambda: w.call("desktop.run_request", w.render, objective=w.objective.text()))
    layout.addLayout(task)
    controls = QHBoxLayout()
    w.enabled = QCheckBox("Enable Desktop Control")
    w.enabled.clicked.connect(w.configure)
    controls.addWidget(w.enabled)
    controls.addStretch()
    button(controls, "Pause", lambda: w.call("desktop.pause"))
    button(controls, "Resume", lambda: w.call("desktop.resume"))
    button(controls, "Cancel", w.bridge.stop_control)
    layout.addLayout(controls)
    w.state, w.phases = QLabel("Ready"), QLabel()
    for label in (w.state, w.phases):
        label.setWordWrap(True)
        layout.addWidget(label)
    w.phases.setAccessibleName("Application workflow progress")
    stop_bar = QToolBar("Desktop safety", w)
    stop_bar.setObjectName("desktopSafetyToolbar")
    stop_bar.setMovable(False)
    stop = QPushButton("STOP CONTROL")
    stop.setObjectName("desktopStopControl")
    stop.setAccessibleName("Emergency stop desktop control")
    stop.setStyleSheet("font-weight: bold; color: #ffb4ab; padding: 10px")
    stop.clicked.connect(w.bridge.stop_control)
    stop_bar.addWidget(stop)
    w.addToolBar(stop_bar)

    split = QSplitter(Qt.Orientation.Horizontal)
    layout.addWidget(split, 1)
    tabs = QTabWidget()
    tabs.setMinimumWidth(260)
    tabs.setMaximumWidth(420)
    split.addWidget(tabs)
    apps = panel(tabs, "Apps")
    button(apps, "Find and open an application", w.applications)
    w.windows = QComboBox()
    w.windows.setAccessibleName("Running application window")
    apps.addWidget(w.windows)
    button(apps, "Refresh windows", w.list_windows)
    button(apps, "Inspect selected window", w.inspect)
    button(apps, "Plan in inspected applications", w.create_plan)
    button(apps, "Execute reviewed plan", lambda: w.call("desktop.execute_plan", w.render))
    apps.addStretch()

    browser = panel(tabs, "Browser")
    button(browser, "Open interactive Chrome", w.open_browser)
    w.tabs, w.url = QComboBox(), QLineEdit()
    w.tabs.setAccessibleName("Interactive browser tab")
    w.url.setPlaceholderText("https://... or a local test page")
    browser.addWidget(w.tabs)
    browser.addWidget(w.url)
    for text, callback in [
        ("Navigate", w.navigate_browser), ("Inspect tab", w.inspect_browser),
        ("New tab", lambda: w.call("desktop.browser_tab", w.render_tabs, action="new_tab", url=w.url.text())),
        ("Switch tab", lambda: w.call("desktop.browser_tab", w.render_browser, action="switch_tab", tab_id=w.tabs.currentData())),
        ("Close tab", lambda: w.call("desktop.browser_tab", w.render_tabs, action="close_tab", tab_id=w.tabs.currentData())),
        ("Review message", w.review_message), ("Upload selected file", w.upload_file),
        ("Download to quarantine", w.download_file), ("Save reviewed download", w.save_download),
        ("Review browser dialog", w.review_browser_dialog)]:
        button(browser, text, callback)
    browser.addStretch()

    tools = panel(tabs, "Tools")
    for text, callback in [
        ("Take screenshot", lambda: w.call("desktop.screenshot", w.show_screenshot)),
        ("Inspect with vision", w.inspect_vision), ("Verify visible label", w.verify_visual_label), ("System media controls", w.media_controls),
        ("Clipboard", w.clipboard_controls), ("Review consequential action", w.review_consequence),
        ("Reset stop", lambda: w.call("desktop.reset", w.render))]:
        button(tools, text, callback)
    tools.addStretch()

    inspector = QWidget()
    body = QVBoxLayout(inspector)
    body.addWidget(QLabel("Observed controls"))
    w.controls = QTreeWidget()
    w.controls.setHeaderLabels(["Control", "Type", "Actions", "State"])
    w.controls.setAccessibleName("Observed application controls")
    w.controls.setMinimumHeight(180)
    body.addWidget(w.controls, 1)
    form = QFormLayout()
    w.action, w.text, w.expected = QComboBox(), QLineEdit(), QLineEdit()
    w.action.addItems(["set_text", "invoke", "select", "expand", "collapse", "scroll", "click", "fill", "search"])
    w.text.setPlaceholderText("Requested text or search query")
    w.expected.setPlaceholderText("Expected visible control after the action")
    form.addRow("Action", w.action)
    form.addRow("Text", w.text)
    form.addRow("Verify", w.expected)
    body.addLayout(form)
    button(body, "Review and perform action", w.perform)
    split.addWidget(inspector)
    split.setSizes([290, 720])
    split.setStretchFactor(1, 1)
