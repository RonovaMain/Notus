"""Backend log window."""
from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout

from ..i18n import tr


class LogDialog(QDialog):
    def __init__(self, lines, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Backend log"))
        self.resize(900, 520)
        lay = QVBoxLayout(self)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(4000)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.view.setStyleSheet("font-family: monospace;")
        self.view.setPlainText("\n".join(lines))
        lay.addWidget(self.view)
        row = QHBoxLayout()
        row.addStretch(1)
        clear = QPushButton(tr("Clear"))
        clear.clicked.connect(self.view.clear)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.close)
        row.addWidget(clear)
        row.addWidget(close)
        lay.addLayout(row)

    def append(self, line: str) -> None:
        self.view.appendPlainText(line)
