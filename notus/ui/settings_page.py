"""Application settings + hardware / backend diagnostics."""
from __future__ import annotations

import subprocess

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from .. import paths
from ..backend import _backend_env, backend_has_gpu
from ..hardware import NO_WINDOW
from ..i18n import tr
from . import theme


def _card() -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("Card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(10)
    return f, lay


class SettingsPage(QWidget):
    theme_changed = pyqtSignal(dict)
    modules_changed = pyqtSignal()
    devices_requested = pyqtSignal()

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Page")
        self.ctx = ctx
        s = ctx.store.s
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner.setObjectName("ScrollInner")
        col = QVBoxLayout(inner)
        col.setSpacing(14)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        t = QLabel(tr("Settings"))
        t.setObjectName("Title")
        col.addWidget(t)

        # appearance
        card, lay = _card()
        h = QLabel(tr("Appearance"))
        h.setObjectName("H2")
        lay.addWidget(h)
        g = QGridLayout()
        g.setHorizontalSpacing(18)
        g.setVerticalSpacing(10)
        g.setColumnStretch(1, 1)
        lay.addLayout(g)
        self.lang = QComboBox()
        for label, v in (("Auto", "auto"), ("English", "en"), ("Русский", "ru")):
            self.lang.addItem(label, v)
        self.lang.setCurrentIndex(max(0, self.lang.findData(s.language)))
        self.theme = QComboBox()
        for label, v in ((tr("Dark"), "dark"), (tr("Light"), "light")):
            self.theme.addItem(label, v)
        self.theme.setCurrentIndex(max(0, self.theme.findData(s.theme)))
        self.accent = QComboBox()
        for name in theme.ACCENTS:
            self.accent.addItem(name.capitalize(), name)
        self.accent.setCurrentIndex(max(0, self.accent.findData(s.accent)))
        self.show_think = QCheckBox(tr("Show the model's thinking text in answers (collapsed)"))
        self.show_think.setChecked(s.show_thinking)
        self.font_spin = QSpinBox()
        self.font_spin.setRange(8, 16)
        self.font_spin.setValue(s.font_size)
        for i, (lab, w) in enumerate(((tr("Language (restart required)"), self.lang), (tr("Theme"), self.theme),
                                      (tr("Accent colour"), self.accent), (tr("Font size"), self.font_spin))):
            g.addWidget(QLabel(lab), i, 0)
            g.addWidget(w, i, 1)
        g.addWidget(self.show_think, 4, 1)
        col.addWidget(card)

        # backend
        card, lay = _card()
        h = QLabel(tr("Backend & behaviour"))
        h.setObjectName("H2")
        lay.addWidget(h)
        g = QGridLayout()
        g.setHorizontalSpacing(18)
        g.setVerticalSpacing(10)
        g.setColumnStretch(1, 1)
        lay.addLayout(g)
        self.backend = QLineEdit(s.backend_dir)
        self.backend.setPlaceholderText(tr("Automatic (the 'backend' folder next to Notus)"))
        b_browse = QPushButton(tr("Browse…"))
        b_browse.clicked.connect(self._browse_backend)
        brow = QHBoxLayout()
        brow.addWidget(self.backend, 1)
        brow.addWidget(b_browse)
        self.device = QComboBox()
        b_detect = QPushButton(tr("Detect devices"))
        b_detect.clicked.connect(self.devices_requested.emit)
        drow = QHBoxLayout()
        drow.addWidget(self.device, 1)
        drow.addWidget(b_detect)
        self.port = QSpinBox()
        self.port.setRange(0, 65535)
        self.port.setSpecialValueText(tr("Automatic"))
        self.port.setValue(s.port)
        self.idle = QSpinBox()
        self.idle.setRange(0, 1440)
        self.idle.setSpecialValueText(tr("Never"))
        self.idle.setSuffix(" " + tr("min"))
        self.idle.setValue(s.auto_unload_minutes)
        g.addWidget(QLabel(tr("Backend folder")), 0, 0)
        g.addLayout(brow, 0, 1)
        g.addWidget(QLabel(tr("Compute device")), 1, 0)
        g.addLayout(drow, 1, 1)
        g.addWidget(QLabel(tr("Internal backend port")), 2, 0)
        g.addWidget(self.port, 2, 1)
        g.addWidget(QLabel(tr("Unload the model when idle for")), 3, 0)
        g.addWidget(self.idle, 3, 1)
        note = QLabel(tr("The backend only listens on 127.0.0.1 (this computer). Notus never connects to the internet."))
        note.setObjectName("Muted")
        note.setWordWrap(True)
        lay.addWidget(note)
        col.addWidget(card)

        # modules
        card, lay = _card()
        h = QLabel(tr("Modules"))
        h.setObjectName("H2")
        lay.addWidget(h)
        self.module_boxes = {}
        for key, label in (("mod_vision", tr("Images (vision models)")),
                           ("mod_files", tr("File attachments (documents, PDF, DOCX)")),
                           ("mod_assistants", tr("Assistants")),
                           ("mod_thinking", tr("Thinking switch")),
                           ("mod_share", tr("Remote access & API page")),
                           ("mod_monitor", tr("Live RAM / VRAM monitor in the status bar"))):
            cb = QCheckBox(label)
            cb.setChecked(getattr(s, key))
            lay.addWidget(cb)
            self.module_boxes[key] = cb
        note = QLabel(tr("A disabled module is not loaded and uses no memory or processor time. "
                         "Vision is additionally switched on per model in “Models”."))
        note.setObjectName("Muted")
        note.setWordWrap(True)
        lay.addWidget(note)
        col.addWidget(card)

        row = QHBoxLayout()
        row.addStretch(1)
        apply_btn = QPushButton(tr("Apply"))
        apply_btn.setObjectName("Primary")
        apply_btn.clicked.connect(self.apply)
        row.addWidget(apply_btn)
        col.addLayout(row)

        # diagnostics
        card, lay = _card()
        h = QLabel(tr("System & diagnostics"))
        h.setObjectName("H2")
        lay.addWidget(h)
        self.hw_lbl = QLabel()
        self.hw_lbl.setWordWrap(True)
        self.hw_lbl.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.hw_lbl)
        b_test = QPushButton(tr("Test backend"))
        b_test.clicked.connect(self.test_backend)
        lay.addWidget(b_test, 0, Qt.AlignmentFlag.AlignLeft)
        self.test_out = QPlainTextEdit()
        self.test_out.setReadOnly(True)
        self.test_out.setFixedHeight(150)
        self.test_out.setStyleSheet("font-family: monospace;")
        self.test_out.hide()
        lay.addWidget(self.test_out)
        col.addWidget(card)
        col.addStretch(1)
        self.populate_devices()
        self.refresh_hw()

    def _browse_backend(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Folder with llama-server"), self.backend.text())
        if d:
            self.backend.setText(d)

    def apply(self) -> None:
        s = self.ctx.store.s
        s.language, s.theme = self.lang.currentData(), self.theme.currentData()
        s.accent, s.font_size = self.accent.currentData(), self.font_spin.value()
        for key, cb in self.module_boxes.items():
            setattr(s, key, cb.isChecked())
        old_backend = s.backend_dir
        s.backend_dir, s.port = self.backend.text().strip(), self.port.value()
        s.device = self.device.currentData() or "auto"
        s.auto_unload_minutes = self.idle.value()
        s.show_thinking = self.show_think.isChecked()
        self.ctx.store.save()
        colors = theme.apply(QApplication.instance(), s.theme, s.accent, s.font_size)
        self.ctx.colors = colors
        self.theme_changed.emit(colors)
        self.modules_changed.emit()
        if s.backend_dir != old_backend:
            self.devices_requested.emit()

    def populate_devices(self) -> None:
        cur = self.ctx.store.s.device
        self.device.blockSignals(True)
        self.device.clear()
        self.device.addItem(tr("Automatic (best GPU)"), "auto")
        self.device.addItem(tr("CPU only"), "cpu")
        for d in self.ctx.devices:
            self.device.addItem("%s — %s (%.1f GB)" % (d.dev_id, d.name, d.total_mb / 1024), d.dev_id)
        self.device.setCurrentIndex(max(0, self.device.findData(cur)))
        self.device.blockSignals(False)

    def refresh_hw(self) -> None:
        hw = self.ctx.hw
        c = self.ctx.colors
        rows = [
            ("CPU", "%s — %d %s / %d %s" % (hw.cpu_name, hw.cores_physical, tr("cores"), hw.cores_logical, tr("threads"))),
            ("AVX / AVX2", "%s / %s" % (self._yn(hw.avx), self._yn(hw.avx2))),
            ("RAM", "%.1f GB" % (hw.ram_total_mb / 1024)),
        ]
        if self.ctx.devices:
            for g in self.ctx.devices:
                rows.append((g.dev_id, "%s — %.1f GB" % (g.name, g.total_mb / 1024)))
        else:
            rows.append(("GPU", tr("No GPU detected by the backend (CPU mode)")))
        exe = paths.find_backend_exe("llama-server", self.ctx.store.s.backend_dir)
        if exe:
            rows.append((tr("Backend"), "%s — GPU: %s" % (exe, self._yn(backend_has_gpu(exe.parent)))))
        else:
            rows.append((tr("Backend"), "<span style='color:%s'>%s</span>" % (c["danger"], tr("not found"))))
        rows.append((tr("Data folder"), str(paths.data_dir()) + (" (portable)" if paths.is_portable() else "")))
        self.hw_lbl.setText("<br>".join("<b>%s:</b> %s" % r for r in rows))

    @staticmethod
    def _yn(v) -> str:
        return "?" if v is None else (tr("yes") if v else tr("no"))

    def test_backend(self) -> None:
        exe = paths.find_backend_exe("llama-server", self.ctx.store.s.backend_dir)
        self.test_out.show()
        if not exe:
            self.test_out.setPlainText(tr("llama-server was not found."))
            return
        out = []
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for flags in (["--version"], ["--list-devices"]):
                try:
                    r = subprocess.run([str(exe)] + flags, capture_output=True, timeout=60, cwd=str(exe.parent),
                                       creationflags=NO_WINDOW, env=_backend_env(exe.parent), stdin=subprocess.DEVNULL)
                    out.append("$ llama-server %s  (exit %d)\n%s" % (flags[0], r.returncode,
                               (r.stdout + r.stderr).decode("utf-8", "replace").strip()))
                except (OSError, subprocess.SubprocessError) as e:
                    out.append("$ llama-server %s\n%s" % (flags[0], e))
        finally:
            QApplication.restoreOverrideCursor()
        self.test_out.setPlainText("\n\n".join(out))
