"""Harmless accessibility fixture; no OLIVE adapter exists for this application."""

import sys
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLineEdit, QPushButton, QLabel

app = QApplication(sys.argv)
window = QWidget()
window.setWindowTitle("OLIVE Generic Accessibility Acceptance")
layout = QVBoxLayout(window)
editor = QLineEdit()
editor.setAccessibleName("Search" if "--search" in sys.argv else "Acceptance text")
layout.addWidget(editor)
label = QLabel("Waiting")
def submitted():
    if "--message" in sys.argv:
        layout.addWidget(QLabel(editor.text()))
        editor.clear()
    else:
        label.setText("Search result: " + editor.text())
editor.returnPressed.connect(submitted)
layout.addWidget(label)
button = QPushButton("Apply test text")
button.clicked.connect(lambda: label.setText("Verified " + editor.text()))
layout.addWidget(button)
window.resize(500, 220)
window.show()
app.exec()
