"""Reusable widgets: chat bubbles, chat view, slider+spin, memory bar."""
from __future__ import annotations

import html

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath
from PyQt6.QtWidgets import (QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QScrollArea,
                             QSizePolicy, QSlider, QVBoxLayout, QWidget)

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
        self.setObjectName("UserBubble" if role == "user" else "BotBubble")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(6)
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
        lay.addWidget(self.think)
        lay.addWidget(self.body)
        lay.addWidget(self.meta)

    def set_content(self, text: str, reasoning: str = "") -> None:
        if self.role == "user":
            self.body.setText(html.escape(text).replace("\n", "<br>"))
        else:
            self.body.setText(markdown_lite.render(text, self.c) if text else "<span style='color:%s'>…</span>" % self.c["muted"])
        if reasoning:
            self.think.setText("<i style='color:%s'>%s %s</i>" % (
                self.c["muted"], html.escape(tr("Thinking:")), html.escape(reasoning).replace("\n", "<br>")))
            self.think.show()
        else:
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
        self._stick = v >= self.verticalScrollBar().maximum() - 24

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
        p.drawText(QRectF(0, 0, w, 18), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), self.title)
        right = "%.1f / %.1f GB" % (used / 1024, self.capacity / 1024) if self.capacity else "%.1f GB" % (used / 1024)
        p.setPen(QColor(self.c["danger"] if over else self.c["muted"]))
        p.drawText(QRectF(0, 0, w, 18), int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), right)
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
            p.drawText(QRectF(x + 14, 42, w, 18), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), text)
            x += 14 + fm.horizontalAdvance(text) + 16
