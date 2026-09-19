"""Local role settings and concise hardware-specific benchmark results."""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QSpinBox, QPushButton, QLabel, QTableWidgetItem
from ..components.common import table


class ModelStackDialog(QDialog):
    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self.bridge, self.snapshot = bridge, None
        self.setWindowTitle("OLIVE — Local model stack")
        self.resize(1050, 600)
        layout = QVBoxLayout(self)
        self.mode = QComboBox()
        self.mode.addItems(["Automatic", "Performance", "Balanced", "Quality"])
        layout.addWidget(self.mode)
        self.table = table(["Role", "Selected", "Manual override", "Context tokens", "Measured quality / latency"])
        layout.addWidget(self.table, 1)
        self.status = QLabel("Benchmarks use small local fixtures and only installed models.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        for name, callback in [("Refresh", self.refresh), ("Save role settings", self.save),
                               ("Benchmark selected stack", self.benchmark), ("Stop benchmark", self.stop)]:
            button = QPushButton(name)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        bridge.event.connect(self.event)
        self.refresh()

    def refresh(self):
        self.bridge.call("models.refresh", self.loaded)

    def loaded(self, value, error):
        if not value:
            self.status.setText(error)
            return
        self.snapshot = value
        self.mode.setCurrentText(value["policy"]["mode"])
        self.table.setRowCount(len(value["assignments"]))
        for row, item in enumerate(value["assignments"]):
            self.table.setItem(row, 0, QTableWidgetItem(item["role"]))
            self.table.setItem(row, 1, QTableWidgetItem(item["model"]))
            combo = QComboBox()
            combo.addItems([""] + value["installed"])
            combo.setCurrentText(item["override"])
            self.table.setCellWidget(row, 2, combo)
            context = QSpinBox()
            context.setRange(1024, 65536)
            context.setValue(item["context"])
            self.table.setCellWidget(row, 3, context)
            measured = item["benchmark"]
            text = f"{measured['quality']:.0%} / {measured['latency_ms'] / 1000:.1f}s · {measured['last_benchmark'][:10]}" if measured else "Not measured"
            self.table.setItem(row, 4, QTableWidgetItem(text))
        self.status.setText(f"Managed model: {value['residency']['managed_model'] or 'None'} · "
                            f"Queued requests: {value['residency']['waiting']} · Results apply to this machine and these fixtures.")

    def save(self):
        if not self.snapshot:
            return
        policy = dict(self.snapshot["policy"])
        policy.update(mode=self.mode.currentText(), overrides={}, contexts={})
        for row in range(self.table.rowCount()):
            role = self.table.item(row, 0).text()
            policy["overrides"][role] = self.table.cellWidget(row, 2).currentText()
            policy["contexts"][role] = self.table.cellWidget(row, 3).value()
        self.bridge.call("models.save", self.loaded, policy=policy)

    def benchmark(self):
        if self.snapshot:
            names = list(dict.fromkeys(item["model"] for item in self.snapshot["assignments"]
                                      if item["role"] != "embedding" and item["model"] != "Unavailable"))
            for name in ("qwen3-coder:30b", "devstral:24b"):
                if name in self.snapshot["installed"] and name not in names:
                    names.append(name)
            self.bridge.call("models.benchmark", lambda value, error: self.refresh(), models=names[:6])

    def stop(self):
        self.bridge.call("models.stop_benchmark")

    def event(self, topic, value):
        if topic == "benchmark":
            self.status.setText(f"{value['model']} · {value['fixture']} · {value.get('status', 'measured')}")
