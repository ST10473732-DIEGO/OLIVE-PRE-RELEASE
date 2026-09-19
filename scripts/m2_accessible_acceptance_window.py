"""Explicitly launched local target; no network, persistence or automation API.

Standard Qt controls only. This external fixture does not change OLIVE's UI.
"""
import sys
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget


class AcceptanceWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('OLIVE M2 accessible acceptance target')
        self.setAccessibleName('OLIVE M2 accessible acceptance target')
        layout = QVBoxLayout(self)
        prompt = QLabel('Acceptance text')
        self.editor = QLineEdit()
        self.editor.setObjectName('acceptance_text')
        self.editor.setAccessibleName('Acceptance text')
        prompt.setBuddy(self.editor)
        self.button = QPushButton('Check text')
        self.button.setObjectName('check_text')
        self.button.setAccessibleName('Check text')
        self.result = QLabel('Not checked')
        self.result.setObjectName('acceptance_result')
        self.result.setAccessibleName('Not checked')
        self.result.setAccessibleDescription('Acceptance result')
        for widget in (prompt, self.editor, self.button, self.result):
            layout.addWidget(widget)
        self.button.clicked.connect(self.check_text)
        self.resize(540, 220)

    def check_text(self):
        message = ('Verified: OLIVE local acceptance'
                   if self.editor.text() == 'OLIVE local acceptance'
                   else 'Text does not match the acceptance phrase')
        self.result.setText(message)
        self.result.setAccessibleName(message)


def main():
    app = QApplication(sys.argv)
    window = AcceptanceWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
