"""Qt-native offline code editor. File operations remain in application services."""

import re
from PySide6.QtCore import Qt, QRect, QSize, Signal, QEvent
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
from PySide6.QtWidgets import QPlainTextEdit, QWidget, QTextEdit, QApplication


class SyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.language = "text"
        self.rules = [
            (
                r"\b(?:class|def|return|if|else|elif|for|while|import|from|as|async|await|try|except|finally|with|yield|in|is|not|and|or|None|True|False|public|private|static|void|new|using|namespace|var|let|const|function|export|interface|extends|async|await|fn|use|impl|struct|match|mut)\b",
                "#82b5f6",
            ),
            (r"\b\d+(?:\.\d+)?\b", "#c0a1ed"),
            (r'"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27', "#9ccc98"),
            (r"(?://|#).*$", "#8793a5"),
        ]

    def highlightBlock(self, text):
        if self.language == "text":
            return
        for pattern, color in self.rules:
            if QApplication.palette().base().color().lightness() > 128:
                color = {
                    "#82b5f6": "#185b9e",
                    "#c0a1ed": "#7544a3",
                    "#9ccc98": "#28753b",
                    "#8793a5": "#596b7d",
                }[color]
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_line_numbers(event)


class NativeEditor(QPlainTextEdit):
    ai_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleName("Source code editor")
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFont(QFont("Consolas", 11))
        self.tab_spaces = 4
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * self.tab_spaces)
        self.highlighter = SyntaxHighlighter(self.document())
        self.numbers = LineNumberArea(self)
        self.blockCountChanged.connect(self.update_margin)
        self.updateRequest.connect(self.update_numbers)
        self.cursorPositionChanged.connect(self.highlight_current)
        self.diagnostics = []
        self.update_margin()
        self.highlight_current()

    def get_text(self):
        return self.toPlainText()

    def set_text(self, text):
        self.setPlainText(text)
        self.document().setModified(False)

    def selected_text(self):
        return self.textCursor().selectedText().replace("\u2029", "\n")

    def cursor_position(self):
        return (self.textCursor().blockNumber() + 1, self.textCursor().positionInBlock() + 1)

    def set_language(self, language):
        self.highlighter.language = language
        self.highlighter.rehighlight()

    def set_diagnostics(self, diagnostics):
        self.diagnostics = diagnostics
        self.highlight_current()

    def save_state(self):
        return {"line": self.cursor_position()[0], "column": self.cursor_position()[1]}

    def set_read_only(self, value):
        self.setReadOnly(value)

    def focus(self):
        self.setFocus()

    def go_to_line(self, line, column=1):
        block = self.document().findBlockByNumber(max(0, min(self.blockCount() - 1, line - 1)))
        cursor = QTextCursor(block)
        cursor.movePosition(
            QTextCursor.MoveOperation.Right,
            QTextCursor.MoveMode.MoveAnchor,
            max(0, min(len(block.text()), column - 1)),
        )
        self.setTextCursor(cursor)
        self.centerCursor()
        self.setFocus()

    def line_number_width(self):
        return 16 + self.fontMetrics().horizontalAdvance("9") * len(str(max(1, self.blockCount())))

    def update_margin(self, *args):
        self.setViewportMargins(self.line_number_width(), 0, 0, 0)

    def update_numbers(self, rect, dy):
        if dy:
            self.numbers.scroll(0, dy)
        else:
            self.numbers.update(0, rect.y(), self.numbers.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_margin()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        rect = self.contentsRect()
        self.numbers.setGeometry(QRect(rect.left(), rect.top(), self.line_number_width(), rect.height()))

    def paint_line_numbers(self, event):
        painter = QPainter(self.numbers)
        painter.fillRect(event.rect(), self.palette().window())
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(self.palette().placeholderText().color())
                painter.drawText(
                    0,
                    top,
                    self.numbers.width() - 6,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    str(number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            number += 1

    def highlight_current(self):
        selections = []
        current = QTextEdit.ExtraSelection()
        current.format.setBackground(QColor(100, 140, 200, 22))
        current.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        current.cursor = self.textCursor()
        current.cursor.clearSelection()
        selections.append(current)
        for diagnostic in self.diagnostics[:500]:
            line = int(diagnostic.get("line") or 1)
            block = self.document().findBlockByNumber(line - 1)
            if not block.isValid():
                continue
            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(block)
            selection.cursor.select(QTextCursor.SelectionType.LineUnderCursor)
            selection.format.setUnderlineColor(QColor("#e37f85"))
            selection.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
            selections.append(selection)
        self.setExtraSelections(selections)

    def keyPressEvent(self, event):
        if self.isReadOnly():
            super().keyPressEvent(event)
            return
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            line = self.textCursor().block().text()
            indent = re.match(r"\s*", line).group(0)
            if line.rstrip().endswith((":", "{")):
                indent += " " * self.tab_spaces
            super().keyPressEvent(event)
            self.insertPlainText(indent)
            return
        if event.key() == Qt.Key.Key_Tab and not event.modifiers():
            self.insertPlainText(" " * self.tab_spaces)
            return
        super().keyPressEvent(event)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and hasattr(self, "highlighter"):
            self.highlighter.rehighlight()

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        menu.addSeparator()
        for name in (
            "Explain selection",
            "Fix selection",
            "Refactor selection",
            "Generate tests",
            "Ask OLIVE",
        ):
            menu.addAction(name, lambda name=name: self.ai_requested.emit(name))
        menu.exec(event.globalPos())
