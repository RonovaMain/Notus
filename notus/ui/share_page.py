"""Remote access page: local API (VS Code, scripts) and the web chat for phones / other computers."""
from __future__ import annotations

import io
import secrets
import time

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from ..i18n import tr
from ..share import lan_addresses

try:                                    # optional: QR code for the phone link
    import segno
except ImportError:                     # pragma: no cover
    segno = None


def _card() -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("Card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(10)
    return f, lay


def _copy(text: str) -> None:
    QApplication.clipboard().setText(text)


class SharePage(QWidget):
    def __init__(self, ctx, share, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Page")
        self.ctx, self.share = ctx, share
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

        t = QLabel(tr("Remote access & API"))
        t.setObjectName("Title")
        col.addWidget(t)
        intro = QLabel(tr("Let your phone, laptop or VS Code use the model that runs on this computer. "
                          "Nothing leaves your own network."))
        intro.setObjectName("Muted")
        intro.setWordWrap(True)
        col.addWidget(intro)

        # --- sharing
        card, lay = _card()
        h = QLabel(tr("Sharing"))
        h.setObjectName("H2")
        lay.addWidget(h)
        self.enable = QCheckBox(tr("Enable sharing (OpenAI-compatible API + web chat)"))
        self.enable.setChecked(s.share_enabled)
        lay.addWidget(self.enable)
        g = QGridLayout()
        g.setHorizontalSpacing(18)
        g.setVerticalSpacing(10)
        g.setColumnStretch(1, 1)
        lay.addLayout(g)
        self.mode = QComboBox()
        self.mode.addItem(tr("Only this computer (127.0.0.1)"), False)
        self.mode.addItem(tr("Devices on my local network (phone, laptop)"), True)
        self.mode.setCurrentIndex(1 if s.share_lan else 0)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(s.share_port)
        self.key = QLineEdit(s.share_key)
        self.key.setPlaceholderText(tr("empty = no password"))
        b_gen = QPushButton(tr("Generate"))
        b_gen.clicked.connect(self._generate_key)
        b_ckey = QPushButton(tr("Copy"))
        b_ckey.clicked.connect(lambda: _copy(self.key.text()))
        krow = QHBoxLayout()
        krow.addWidget(self.key, 1)
        krow.addWidget(b_gen)
        krow.addWidget(b_ckey)
        for i, (lab, w) in enumerate(((tr("Who can connect"), self.mode), (tr("Port"), self.port))):
            g.addWidget(QLabel(lab), i, 0)
            g.addWidget(w, i, 1)
        g.addWidget(QLabel(tr("Access key")), 2, 0)
        g.addLayout(krow, 2, 1)
        self.allow_switch = QCheckBox(tr("Clients may switch or unload models"))
        self.allow_switch.setChecked(s.share_allow_switch)
        self.autoload = QCheckBox(tr("Load a model automatically when a request arrives"))
        self.autoload.setChecked(s.share_autoload)
        self.webui = QCheckBox(tr("Serve the web chat page (open the address in a browser)"))
        self.webui.setChecked(s.share_webui)
        for cb in (self.allow_switch, self.autoload, self.webui):
            lay.addWidget(cb)
        self.warn = QLabel()
        self.warn.setWordWrap(True)
        self.warn.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.warn)
        row = QHBoxLayout()
        self.status = QLabel()
        self.status.setWordWrap(True)
        b_apply = QPushButton(tr("Apply"))
        b_apply.setObjectName("Primary")
        b_apply.clicked.connect(self.apply)
        row.addWidget(self.status, 1)
        row.addWidget(b_apply)
        lay.addLayout(row)
        hint = QLabel(tr("Windows may ask to allow Notus through the firewall — allow “Private networks”. "
                         "Phone and computer must be on the same Wi-Fi / router. For access from outside your home use a VPN "
                         "(Tailscale, WireGuard) — do not expose this port to the internet."))
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        col.addWidget(card)

        # --- web chat
        card, lay = _card()
        h = QLabel(tr("Web chat for your phone or another computer"))
        h.setObjectName("H2")
        lay.addWidget(h)
        wrow = QHBoxLayout()
        wrow.setSpacing(16)
        self.qr = QLabel()
        self.qr.setFixedSize(190, 190)
        self.qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wrow.addWidget(self.qr)
        wcol = QVBoxLayout()
        self.urls_lbl = QLabel()
        self.urls_lbl.setTextFormat(Qt.TextFormat.RichText)
        self.urls_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.urls_lbl.setWordWrap(True)
        wcol.addWidget(self.urls_lbl)
        brow = QHBoxLayout()
        b_open = QPushButton(tr("Open in browser"))
        b_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self._web_url(False))))
        b_cl = QPushButton(tr("Copy link"))
        b_cl.clicked.connect(lambda: _copy(self._web_url(True)))
        brow.addWidget(b_open)
        brow.addWidget(b_cl)
        brow.addStretch(1)
        wcol.addLayout(brow)
        self.qr_hint = QLabel(tr("Scan the code with your phone camera. The link already contains the access key."))
        self.qr_hint.setObjectName("Muted")
        self.qr_hint.setWordWrap(True)
        wcol.addWidget(self.qr_hint)
        wcol.addStretch(1)
        wrow.addLayout(wcol, 1)
        lay.addLayout(wrow)
        col.addWidget(card)

        # --- API
        card, lay = _card()
        h = QLabel(tr("Use as an API (VS Code, Continue, scripts)"))
        h.setObjectName("H2")
        lay.addWidget(h)
        ag = QGridLayout()
        ag.setHorizontalSpacing(12)
        ag.setColumnStretch(1, 1)
        self.base_edit = QLineEdit()
        self.base_edit.setReadOnly(True)
        self.model_pick = QComboBox()
        self.model_pick.currentIndexChanged.connect(self._refresh_texts)
        for i, (lab, w, val) in enumerate(((tr("Base URL"), self.base_edit, lambda: self.base_edit.text()),
                                           (tr("Model ID"), self.model_pick, lambda: self.model_pick.currentText()))):
            ag.addWidget(QLabel(lab), i, 0)
            ag.addWidget(w, i, 1)
            b = QPushButton(tr("Copy"))
            b.clicked.connect(lambda _=False, f=val: _copy(f()))
            ag.addWidget(b, i, 2)
        lay.addLayout(ag)
        self.howto = QPlainTextEdit()
        self.howto.setReadOnly(True)
        self.howto.setFixedHeight(300)
        self.howto.setStyleSheet("font-family: monospace;")
        lay.addWidget(self.howto)
        b_cp = QPushButton(tr("Copy instructions"))
        b_cp.clicked.connect(lambda: _copy(self.howto.toPlainText()))
        lay.addWidget(b_cp, 0, Qt.AlignmentFlag.AlignLeft)
        col.addWidget(card)

        # --- activity
        card, lay = _card()
        h = QLabel(tr("Activity"))
        h.setObjectName("H2")
        lay.addWidget(h)
        self.activity = QLabel()
        lay.addWidget(self.activity)
        col.addWidget(card)
        col.addStretch(1)

        for w in (self.enable, self.allow_switch, self.autoload, self.webui):
            w.toggled.connect(self._refresh_warn)
        self.mode.currentIndexChanged.connect(self._refresh_warn)
        self.key.textChanged.connect(self._refresh_warn)
        self.port.valueChanged.connect(self._refresh_warn)
        share.status_changed.connect(self._refresh_status)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_activity)
        self._timer.start(2000)
        self.refresh_models()
        self._refresh_warn()
        self._refresh_status()

    # ---- helpers -------------------------------------------------------
    def _generate_key(self) -> None:
        self.key.setText(secrets.token_urlsafe(18))

    def _host(self) -> str:
        if self.mode.currentData():
            addrs = lan_addresses()
            return addrs[0][1] if addrs else "127.0.0.1"
        return "127.0.0.1"

    def _web_url(self, with_key: bool) -> str:
        url = "http://%s:%d/" % (self._host(), self.port.value())
        return url + ("#key=" + self.key.text() if with_key and self.key.text() else "")

    def refresh_models(self) -> None:
        cur = self.model_pick.currentText()
        self.model_pick.blockSignals(True)
        self.model_pick.clear()
        for m in self.ctx.store.s.models:
            self.model_pick.addItem(m.name)
        i = self.model_pick.findText(cur)
        self.model_pick.setCurrentIndex(max(0, i))
        self.model_pick.blockSignals(False)
        self._refresh_texts()

    def _refresh_warn(self, *_a) -> None:
        c = self.ctx.colors
        lan = bool(self.mode.currentData())
        msg = ""
        if lan and not self.key.text():
            msg = "<span style='color:%s'>%s</span>" % (c["danger"], tr("Anyone on your network could use the model. Set an access key."))
        elif not lan:
            msg = tr("Only programs on this computer can connect. Choose “Devices on my local network” to use your phone.")
        self.warn.setText(msg)
        self._refresh_texts()

    def _refresh_texts(self, *_a) -> None:
        host, port = self._host(), self.port.value()
        base = "http://%s:%d/v1" % (host, port)
        self.base_edit.setText(base)
        key = self.key.text() or "notus"
        model = self.model_pick.currentText() or "my-model"
        addrs = lan_addresses() if self.mode.currentData() else []
        lines = ["<b>%s</b>" % tr("Web chat addresses:")]
        for u in ([("http://%s:%d/" % (a, port)) for _i, a in addrs] or ["http://127.0.0.1:%d/" % port]):
            lines.append("<a href='%s'>%s</a>" % (u, u))
        self.urls_lbl.setText("<br>".join(lines))
        self.urls_lbl.setOpenExternalLinks(True)
        # QR code
        pm = None
        if segno is not None:
            try:
                buf = io.BytesIO()
                segno.make(self._web_url(True), error="m").save(buf, kind="png", scale=5, border=2)
                pm = QPixmap()
                pm.loadFromData(buf.getvalue())
            except Exception:
                pm = None
        if pm is not None and not pm.isNull():
            self.qr.setPixmap(pm.scaled(190, 190, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))
            self.qr_hint.show()
        else:
            self.qr.setText("QR\n(" + tr("install the 'segno' package") + ")")
            self.qr_hint.hide()
        self.howto.setPlainText(
            "VS Code — GitHub Copilot Chat\n"
            "  Command Palette → “Chat: Manage Language Models” → Add Models →\n"
            "  “OpenAI Compatible” (in VS Code Insiders: “Custom Endpoint”), then enter:\n"
            "    URL:      %(base)s\n    API key:  %(key)s\n    Model ID: %(model)s\n"
            "  Only the chat works this way; inline code suggestions stay with Copilot.\n\n"
            "Continue / Cline / Roo Code (VS Code extensions)\n"
            "  Provider “OpenAI-compatible”, the same URL, key and model. Continue config.yaml:\n"
            "    models:\n      - name: Notus\n        provider: openai\n        model: %(model)s\n"
            "        apiBase: %(base)s\n        apiKey: %(key)s\n\n"
            "Any other program / script\n"
            "  curl %(base)s/chat/completions -H \"Authorization: Bearer %(key)s\" -H \"Content-Type: application/json\" \\\n"
            "    -d '{\"model\":\"%(model)s\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}'\n\n"
            "%(note)s" % {"base": base, "key": key, "model": model,
                          "note": tr("No key is set: any text works as the API key.") if not self.key.text() else
                                  tr("Tools that can call functions need a model that supports tool calling.")})

    def _refresh_status(self) -> None:
        c = self.ctx.colors
        if self.share.error:
            self.status.setText("<span style='color:%s'>%s</span>" % (c["danger"], self.share.error))
        elif self.share.gw is not None:
            self.status.setText("<span style='color:%s'>●</span> %s %s:%d" % (
                c["ok"], tr("Running on"), self.share.gw.host, self.share.gw.port))
        else:
            self.status.setText("<span style='color:%s'>●</span> %s" % (c["muted"], tr("Sharing is off")))
        self._refresh_texts()

    def _refresh_activity(self) -> None:
        gw = self.share.gw
        if gw is None:
            self.activity.setText(tr("Sharing is off"))
            return
        st = gw.stats
        last = ""
        if st["last_time"]:
            last = " · %s %s (%d %s)" % (tr("last request from"), st["last_client"], int(time.time() - st["last_time"]), tr("s ago"))
        self.activity.setText("%d %s%s" % (st["requests"], tr("requests"), last))

    def apply(self) -> None:
        s = self.ctx.store.s
        if self.mode.currentData() and not self.key.text():
            self._generate_key()
        s.share_enabled, s.share_lan = self.enable.isChecked(), bool(self.mode.currentData())
        s.share_port, s.share_key = self.port.value(), self.key.text()
        s.share_allow_switch, s.share_autoload, s.share_webui = (
            self.allow_switch.isChecked(), self.autoload.isChecked(), self.webui.isChecked())
        self.ctx.store.save()
        self.share.apply()
