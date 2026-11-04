"""Reusable widgets: chat bubbles, chat view, slider+spin, memory bar."""
from __future__ import annotations

import base64
import html

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (QApplication, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton,
                             QScrollArea, QSizePolicy, QSlider, QVBoxLayout, QWidget)

from .. import markdown_lite
from ..i18n import tr


class SliderSpin(QWidget):
    """A slider and a spin box kept in sync; works for ints and floats."""
    valueChanged = pyqtSignal(float)

    def __init__(self, minimum: float, maximum: float, step: float = 1.0, decimals: int = 0, parent=None) -> None:
        super().__init__(parent)
        self._scale = 10 ** decimals
        self._step = step
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.spin = QDoubleSpinBox()
        self.spin.setDecimals(decimals)
        self.spin.setSingleStep(step)
        self.spin.setFixedWidth(92)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.spin)
        self.set_range(minimum, maximum)
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)

    def set_range(self, mn: float, mx: float) -> None:
        for w in (self.slider, self.spin):
            w.blockSignals(True)
        self.spin.setRange(mn, mx)
        self.slider.setRange(int(round(mn * self._scale)), int(round(mx * self._scale)))
        self.slider.setSingleStep(max(1, int(round(self._step * self._scale))))
        self.slider.setPageStep(max(1, int(round((mx - mn) * self._scale / 10))))
        for w in (self.slider, self.spin):
            w.blockSignals(False)

    def _from_slider(self, v: int) -> None:
        val = v / self._scale
        self.spin.blockSignals(True)
        self.spin.setValue(val)
        self.spin.blockSignals(False)
        self.valueChanged.emit(val)

    def _from_spin(self, val: float) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(val * self._scale)))
        self.slider.blockSignals(False)
        self.valueChanged.emit(val)

    def value(self) -> float:
        return self.spin.value()

    def set_value(self, v: float) -> None:
        for w in (self.slider, self.spin):
            w.blockSignals(True)
        self.spin.setValue(v)
        self.slider.setValue(int(round(self.spin.value() * self._scale)))
        for w in (self.slider, self.spin):
            w.blockSignals(False)


class Bubble(QFrame):
    def __init__(self, role: str, colors: dict) -> None:
        super().__init__()
        self.role, self.c = role, colors
        self._raw = ""
        self._think_open = False
        self._think_text = ""
        self.setObjectName("UserBubble" if role == "user" else "BotBubble")
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(6)
        self.attach = QWidget()
        self.attach_lay = QHBoxLayout(self.attach)
        self.attach_lay.setContentsMargins(0, 0, 0, 0)
        self.attach_lay.setSpacing(8)
        self.attach.hide()
        self.think_btn = QPushButton()
        self.think_btn.setObjectName("Chip")
        self.think_btn.setFlat(True)
        self.think_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.think_btn.clicked.connect(self._toggle_think)
        self.think_btn.hide()
        self.think = QLabel()
        self.body = QLabel()
        for lbl in (self.think, self.body):
            lbl.setWordWrap(True)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                        | Qt.TextInteractionFlag.LinksAccessibleByMouse)
            lbl.setOpenExternalLinks(True)
        self.think.hide()
        self.meta = QLabel()
        self.meta.setObjectName("Muted")
        self.meta.hide()
        lay.addWidget(self.attach)
        lay.addWidget(self.think_btn, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self.think)
        lay.addWidget(self.body)
        lay.addWidget(self.meta)

    def _menu(self, pos) -> None:
        menu = QMenu(self)
        act = menu.addAction(tr("Copy message"))
        if menu.exec(self.mapToGlobal(pos)) is act:
            QApplication.clipboard().setText(self._raw)

    def _toggle_think(self) -> None:
        self._think_open = not self._think_open
        self._refresh_think()

    def _refresh_think(self) -> None:
        self.think_btn.setText(("▾ " if self._think_open else "▸ ") + tr("Thinking") + " (%d)" % len(self._think_text))
        self.think.setVisible(self._think_open)

    def set_attachments(self, files, images) -> None:
        while self.attach_lay.count():
            w = self.attach_lay.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
        for u in images or []:
            pm = QPixmap()
            if pm.loadFromData(base64.b64decode(u.split(",", 1)[-1])):
                lbl = QLabel()
                lbl.setPixmap(pm.scaledToHeight(110, Qt.TransformationMode.SmoothTransformation))
                self.attach_lay.addWidget(lbl)
        for f in files or []:
            lbl = QLabel("📎 " + f.get("name", "file"))
            lbl.setStyleSheet("background:%s; border-radius:8px; padding:3px 8px;" % self.c["inline_bg"])
            self.attach_lay.addWidget(lbl)
        self.attach_lay.addStretch(1)
        self.attach.setVisible(bool(images or files))

    def set_content(self, text: str, reasoning: str = "", show_reasoning: bool = True) -> None:
        self._raw = text
        if self.role == "user":
            self.body.setText(html.escape(text).replace("\n", "<br>"))
            self.body.setVisible(bool(text))
            return
        muted = self.c["muted"]
        if text:
            self.body.setText(markdown_lite.render(text, self.c))
        elif reasoning:
            self.body.setText("<span style='color:%s'><i>%s</i></span>" % (muted, html.escape(tr("Thinking…"))))
        else:
            self.body.setText("<span style='color:%s'>…</span>" % muted)
        self._think_text = reasoning
        if reasoning and show_reasoning:
            self.think.setText("<span style='color:%s'><i>%s</i></span>" % (muted, html.escape(reasoning).replace("\n", "<br>")))
            self.think_btn.show()
            self._refresh_think()
        else:
            self.think_btn.hide()
            self.think.hide()

    def set_error(self, text: str) -> None:
        self.body.setText("<span style='color:%s'>%s</span>" % (self.c["danger"], html.escape(text).replace("\n", "<br>")))

    def set_meta(self, text: str) -> None:
        self.meta.setText(text)
        self.meta.setVisible(bool(text))


class ChatView(QScrollArea):
    def __init__(self, colors: dict) -> None:
        super().__init__()
        self.c = colors
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.inner = QWidget()
        self.inner.setObjectName("ScrollInner")
        self.col = QVBoxLayout(self.inner)
        self.col.setContentsMargins(24, 16, 24, 16)
        self.col.setSpacing(12)
        self.hint = QLabel()
        self.hint.setObjectName("Muted")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setWordWrap(True)
        self.col.addWidget(self.hint)
        self.col.addStretch(1)
        self.setWidget(self.inner)
        self.bubbles: list[Bubble] = []
        self._rows: list[QWidget] = []
        self._stick = True
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.verticalScrollBar().rangeChanged.connect(self._on_range)

    def set_hint(self, text: str) -> None:
        self.hint.setText(text)
        self.hint.setVisible(bool(text) and not self.bubbles)

    def _on_scroll(self, v: int) -> None:
        # follow the stream only while the view sits exactly at the bottom
        self._stick = v >= self.verticalScrollBar().maximum() - 2

    def wheelEvent(self, e) -> None:
        if e.angleDelta().y() > 0:          # the user scrolls up: stop following immediately
            self._stick = False
        super().wheelEvent(e)

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key.Key_Up, Qt.Key.Key_PageUp, Qt.Key.Key_Home):
            self._stick = False
        super().keyPressEvent(e)

    def _on_range(self, _mn: int, mx: int) -> None:
        if self._stick:
            self.verticalScrollBar().setValue(mx)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        w = max(320, int(self.viewport().width() * 0.88) - 48)
        for b in self.bubbles:
            b.setMaximumWidth(w)

    def add_bubble(self, role: str) -> Bubble:
        b = Bubble(role, self.c)
        b.setMaximumWidth(max(320, int(self.viewport().width() * 0.88) - 48))
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        if role == "user":
            h.addStretch(1)
            h.addWidget(b)
        else:
            h.addWidget(b)
            h.addStretch(1)
        self.col.insertWidget(self.col.count() - 1, row)
        self.bubbles.append(b)
        self._rows.append(row)
        self.hint.hide()
        self._stick = True
        return b

    def remove_last(self) -> None:
        if self._rows:
            row = self._rows.pop()
            self.bubbles.pop()
            row.setParent(None)
            row.deleteLater()

    def clear(self) -> None:
        while self._rows:
            self.remove_last()
        self.hint.setVisible(bool(self.hint.text()))


class MemoryBar(QWidget):
    """Horizontal stacked bar: [(label, megabytes, colour)] against a capacity."""

    def __init__(self, colors: dict, parent=None) -> None:
        super().__init__(parent)
        self.c = colors
        self.title, self.segs, self.capacity = "", [], 0.0
        self.setMinimumHeight(62)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_data(self, title: str, segs: list, capacity_mb: float) -> None:
        self.title, self.segs, self.capacity = title, segs, capacity_mb
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        used = sum(s[1] for s in self.segs)
        over = self.capacity > 0 and used > self.capacity
        p.setPen(QColor(self.c["text"]))
        p.drawText(QRectF(0, 0, w, 18), (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter).value, self.title)
        right = "%.1f / %.1f GB" % (used / 1024, self.capacity / 1024) if self.capacity else "%.1f GB" % (used / 1024)
        p.setPen(QColor(self.c["danger"] if over else self.c["muted"]))
        p.drawText(QRectF(0, 0, w, 18), (Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter).value, right)
        bar = QRectF(0, 24, w, 12)
        path = QPainterPath()
        path.addRoundedRect(bar, 6, 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.c["border"]))
        p.drawPath(path)
        scale = max(self.capacity, used, 1.0)
        p.save()
        p.setClipPath(path)
        x = 0.0
        for _label, mb, color in self.segs:
            sw = w * mb / scale
            p.setBrush(QColor(color))
            p.drawRect(QRectF(x, bar.top(), sw, bar.height()))
            x += sw
        if over:
            cx = w * self.capacity / scale
            p.setBrush(QColor(self.c["danger"]))
            p.drawRect(QRectF(cx - 1, bar.top(), 2, bar.height()))
        p.restore()
        fm = QFontMetrics(self.font())
        x = 0
        for label, mb, color in self.segs:
            p.setBrush(QColor(color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(x, 46, 9, 9))
            text = "%s %.1f GB" % (label, mb / 1024)
            p.setPen(QColor(self.c["muted"]))
            p.drawText(QRectF(x + 14, 42, w, 18), (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter).value, text)
            x += 14 + fm.horizontalAdvance(text) + 16
