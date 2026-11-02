"""Assistants: reusable roles (system prompt + optional temperature / thinking override)."""
from __future__ import annotations

import uuid

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from .. import assistants as assistants_mod
from ..config import Assistant
from ..i18n import tr
from .widgets import SliderSpin


def _card() -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("Card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(10)
    return f, lay


class AssistantsPage(QWidget):
    assistants_changed = pyqtSignal()

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Page")
        self.ctx = ctx
        self.cur: Assistant | None = None
        self._loading = False
        root = QHBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        left, ll = _card()
        left.setFixedWidth(300)
        t = QLabel(tr("Assistants"))
        t.setObjectName("H2")
        ll.addWidget(t)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._on_row)
        ll.addWidget(self.list, 1)
        b_new = QPushButton(tr("New assistant"))
        b_new.setObjectName("Primary")
        b_new.clicked.connect(self.add_new)
        b_dup = QPushButton(tr("Duplicate"))
        b_dup.clicked.connect(self.duplicate)
        b_del = QPushButton(tr("Delete"))
        b_del.setObjectName("Danger")
        b_del.clicked.connect(self.delete)
        b_rest = QPushButton(tr("Restore built-in assistants"))
        b_rest.clicked.connect(self.restore)
        for b in (b_new, b_dup, b_del, b_rest):
            ll.addWidget(b)
        root.addWidget(left)

        right, rl = _card()
        title = QLabel(tr("Assistant settings"))
        title.setObjectName("Title")
        rl.addWidget(title)
        intro = QLabel(tr("An assistant is a ready-made role: instructions the model always follows. "
                          "Pick one in the chat bar. Use “Image describer” with a vision model for photos, "
                          "“Document analyst” for attached files."))
        intro.setObjectName("Muted")
        intro.setWordWrap(True)
        rl.addWidget(intro)
        self.name = QLineEdit()
        self.name.editingFinished.connect(self._changed)
        self.prompt = QPlainTextEdit()
        self.prompt.setMinimumHeight(220)
        self.prompt.textChanged.connect(self._changed)
        self.use_temp = QCheckBox(tr("Use its own temperature (otherwise the model's setting)"))
        self.use_temp.toggled.connect(self._changed)
        self.temp = SliderSpin(0.0, 2.0, 0.05, 2)
        self.temp.valueChanged.connect(self._changed)
        self.think = QComboBox()
        for label, v in ((tr("Use the chat setting"), "inherit"), (tr("Thinking: auto"), "auto"),
                         (tr("Thinking: on"), "on"), (tr("Thinking: off"), "off")):
            self.think.addItem(label, v)
        self.think.currentIndexChanged.connect(self._changed)
        for lab, w in ((tr("Name"), self.name), (tr("Instructions (system prompt)"), self.prompt)):
            l = QLabel(lab)
            l.setObjectName("Muted")
            rl.addWidget(l)
            rl.addWidget(w)
        rl.addWidget(self.use_temp)
        rl.addWidget(self.temp)
        l = QLabel(tr("Thinking mode"))
        l.setObjectName("Muted")
        rl.addWidget(l)
        rl.addWidget(self.think)
        rl.addStretch(1)
        self.editor = right
        root.addWidget(right, 1)
        self.refresh_list()

    def refresh_list(self, select_id: str | None = None) -> None:
        items = self.ctx.store.s.assistants
        self.list.blockSignals(True)
        self.list.clear()
        for a in items:
            it = QListWidgetItem(a.name)
            it.setData(Qt.ItemDataRole.UserRole, a.id)
            self.list.addItem(it)
        self.list.blockSignals(False)
        target = select_id or (self.cur.id if self.cur else "")
        row = next((i for i, a in enumerate(items) if a.id == target), 0 if items else -1)
        self.list.setCurrentRow(row)
        self._on_row(row)

    def _on_row(self, row: int) -> None:
        items = self.ctx.store.s.assistants
        self.cur = items[row] if 0 <= row < len(items) else None
        self.editor.setVisible(self.cur is not None)
        if self.cur is None:
            return
        a = self.cur
        self._loading = True
        self.name.setText(a.name)
        self.prompt.setPlainText(a.system_prompt)
        self.use_temp.setChecked(a.temperature >= 0)
        self.temp.set_value(a.temperature if a.temperature >= 0 else 0.7)
        self.temp.setEnabled(a.temperature >= 0)
        self.think.setCurrentIndex(max(0, self.think.findData(a.think)))
        self._loading = False

    def _changed(self, *_a) -> None:
        if self._loading or self.cur is None:
            return
        a = self.cur
        a.name = self.name.text().strip() or a.name
        a.system_prompt = self.prompt.toPlainText()
        a.temperature = round(self.temp.value(), 3) if self.use_temp.isChecked() else -1.0
        self.temp.setEnabled(self.use_temp.isChecked())
        a.think = self.think.currentData() or "inherit"
        item = self.list.currentItem()
        if item is not None and item.text() != a.name:
            item.setText(a.name)
        self.ctx.store.save_later()
        self.assistants_changed.emit()

    def add_new(self) -> None:
        a = Assistant(id=uuid.uuid4().hex[:12], name=tr("New assistant"), system_prompt="")
        self.ctx.store.s.assistants.append(a)
        self.ctx.store.save_later()
        self.refresh_list(a.id)
        self.assistants_changed.emit()
        self.name.setFocus()
        self.name.selectAll()

    def duplicate(self) -> None:
        if self.cur is None:
            return
        c = Assistant(id=uuid.uuid4().hex[:12], name=self.cur.name + " " + tr("(copy)"), system_prompt=self.cur.system_prompt,
                      temperature=self.cur.temperature, think=self.cur.think)
        self.ctx.store.s.assistants.append(c)
        self.ctx.store.save_later()
        self.refresh_list(c.id)
        self.assistants_changed.emit()

    def delete(self) -> None:
        if self.cur is None:
            return
        if QMessageBox.question(self, tr("Notus"), tr("Delete the assistant “{name}”?").format(name=self.cur.name)) \
                != QMessageBox.StandardButton.Yes:
            return
        s = self.ctx.store.s
        s.assistants = [a for a in s.assistants if a.id != self.cur.id]
        if s.last_assistant_id == self.cur.id:
            s.last_assistant_id = ""
        self.cur = None
        self.ctx.store.save_later()
        self.refresh_list()
        self.assistants_changed.emit()

    def restore(self) -> None:
        n = assistants_mod.restore_missing(self.ctx.store)
        self.ctx.store.save_later()
        self.refresh_list()
        self.assistants_changed.emit()
        QMessageBox.information(self, tr("Notus"), tr("Restored: {n}").format(n=n))
