"""Chat page: model bar, conversation view, input and generation parameters."""
from __future__ import annotations

import time

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                             QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from ..client import ChatWorker, fit_messages
from ..i18n import tr
from .widgets import ChatView, SliderSpin


class _InputEdit(QPlainTextEdit):
    submitted = pyqtSignal()

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.submitted.emit()
            return
        super().keyPressEvent(e)


class ChatPage(QWidget):
    chat_changed = pyqtSignal(object)
    open_models = pyqtSignal()
    show_log = pyqtSignal()

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Page")
        self.ctx = ctx
        self.chat = None
        self.worker: ChatWorker | None = None
        self._pending = False
        self._buf = ""
        self._rbuf = ""
        self._bubble = None
        self._loading_gen = False
        self._failed = False
        self.last_activity = time.time()
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(50)
        self._flush_timer.timeout.connect(self._flush)
        self._build()
        ctx.server.state_changed.connect(self._on_state)
        ctx.server.failed.connect(self._on_server_failed)
        self.refresh_models()
        self._on_state(ctx.server.state)

    # ---- UI ------------------------------------------------------------
    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        col = QVBoxLayout()
        col.setSpacing(0)
        root.addLayout(col, 1)

        top = QFrame()
        top.setObjectName("Topbar")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(16, 10, 16, 10)
        tl.setSpacing(10)
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(260)
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        self.btn_load = QPushButton()
        self.btn_load.setObjectName("Primary")
        self.btn_load.clicked.connect(self._toggle_load)
        self.pill = QLabel()
        self.btn_log = QPushButton(tr("Log"))
        self.btn_log.clicked.connect(self.show_log.emit)
        self.btn_params = QPushButton(tr("Parameters"))
        self.btn_params.setCheckable(True)
        self.btn_params.setChecked(self.ctx.store.s.show_params_panel)
        self.btn_params.toggled.connect(self._toggle_params)
        tl.addWidget(self.model_combo)
        tl.addWidget(self.btn_load)
        tl.addWidget(self.pill)
        tl.addStretch(1)
        tl.addWidget(self.btn_log)
        tl.addWidget(self.btn_params)
        col.addWidget(top)

        self.view = ChatView(self.ctx.colors)
        self.view.set_hint(tr("Pick a model, press “Load model” and start chatting.\nEverything runs locally on your computer."))
        col.addWidget(self.view, 1)

        bar = QFrame()
        bar.setObjectName("InputBar")
        bl = QVBoxLayout(bar)
        bl.setContentsMargins(16, 12, 16, 10)
        bl.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.input = _InputEdit()
        self.input.setPlaceholderText(tr("Message Notus…  (Enter — send, Shift+Enter — new line)"))
        self.input.setFixedHeight(66)
        self.input.submitted.connect(self.on_send)
        self.btn_send = QPushButton(tr("Send"))
        self.btn_send.setObjectName("Primary")
        self.btn_send.setMinimumWidth(96)
        self.btn_send.clicked.connect(self.on_send)
        self.btn_regen = QPushButton("↻")
        self.btn_regen.setToolTip(tr("Regenerate the last answer"))
        self.btn_regen.clicked.connect(self.on_regen)
        row.addWidget(self.input, 1)
        side = QVBoxLayout()
        side.setSpacing(6)
        side.addWidget(self.btn_send)
        side.addWidget(self.btn_regen)
        row.addLayout(side)
        bl.addLayout(row)
        self.lbl_info = QLabel("")
        self.lbl_info.setObjectName("Muted")
        bl.addWidget(self.lbl_info)
        col.addWidget(bar)

        self.params = self._build_params()
        root.addWidget(self.params)
        self.params.setVisible(self.btn_params.isChecked())

    def _build_params(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("ParamsPanel")
        panel.setFixedWidth(320)
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner.setObjectName("ScrollInner")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(8)
        title = QLabel(tr("Generation"))
        title.setObjectName("H2")
        lay.addWidget(title)

        def add(label: str, widget: QWidget, hint: str = "") -> None:
            l = QLabel(label)
            l.setObjectName("Muted")
            if hint:
                l.setToolTip(hint)
                widget.setToolTip(hint)
            lay.addWidget(l)
            lay.addWidget(widget)

        self.g_temp = SliderSpin(0.0, 2.0, 0.05, 2)
        self.g_top_p = SliderSpin(0.0, 1.0, 0.01, 2)
        self.g_top_k = SliderSpin(0, 200, 1, 0)
        self.g_min_p = SliderSpin(0.0, 1.0, 0.01, 2)
        self.g_rep = SliderSpin(0.8, 2.0, 0.01, 2)
        self.g_max = SliderSpin(16, 32768, 16, 0)
        self.g_seed = QSpinBox()
        self.g_seed.setRange(-1, 2147483647)
        self.g_seed.setSpecialValueText(tr("Random"))
        self.g_system = QPlainTextEdit()
        self.g_system.setFixedHeight(130)
        self.g_system.setPlaceholderText(tr("Optional instructions for the model, e.g. “Answer briefly and in Russian.”"))
        add(tr("Max new tokens"), self.g_max, tr("How many tokens the model may generate per answer."))
        add(tr("Temperature"), self.g_temp, tr("Higher = more creative, lower = more precise."))
        add("Top-P", self.g_top_p)
        add("Top-K", self.g_top_k)
        add("Min-P", self.g_min_p)
        add(tr("Repeat penalty"), self.g_rep, tr("Discourages the model from repeating itself."))
        add(tr("Seed"), self.g_seed, tr("Fixed seed gives reproducible answers."))
        add(tr("System prompt"), self.g_system)
        lay.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        for w in (self.g_temp, self.g_top_p, self.g_top_k, self.g_min_p, self.g_rep, self.g_max):
            w.valueChanged.connect(self._gen_changed)
        self.g_seed.valueChanged.connect(self._gen_changed)
        self.g_system.textChanged.connect(self._gen_changed)
        return panel

    # ---- models / generation settings ----------------------------------
    def current_entry(self):
        return self.ctx.store.get_model(self.model_combo.currentData())

    def refresh_models(self) -> None:
        s = self.ctx.store.s
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for m in s.models:
            self.model_combo.addItem(m.name, m.id)
        if not s.models:
            self.model_combo.addItem(tr("No models — add one in “Models”"), "")
        idx = self.model_combo.findData(s.last_model_id)
        self.model_combo.setCurrentIndex(max(0, idx))
        self.model_combo.blockSignals(False)
        self._on_model_changed()

    def _on_model_changed(self) -> None:
        e = self.current_entry()
        if e:
            self.ctx.store.s.last_model_id = e.id
            self.ctx.store.save_later()
            g = e.gen
            self._loading_gen = True
            self.g_temp.set_value(g.temperature)
            self.g_top_p.set_value(g.top_p)
            self.g_top_k.set_value(g.top_k)
            self.g_min_p.set_value(g.min_p)
            self.g_rep.set_value(g.repeat_penalty)
            self.g_max.set_value(g.max_tokens)
            self.g_seed.setValue(g.seed)
            self.g_system.setPlainText(g.system_prompt)
            self._loading_gen = False
        self._on_state(self.ctx.server.state)

    def _gen_changed(self, *_a) -> None:
        e = self.current_entry()
        if self._loading_gen or not e:
            return
        g = e.gen
        g.temperature, g.top_p = round(self.g_temp.value(), 3), round(self.g_top_p.value(), 3)
        g.top_k, g.min_p = int(self.g_top_k.value()), round(self.g_min_p.value(), 3)
        g.repeat_penalty, g.max_tokens = round(self.g_rep.value(), 3), int(self.g_max.value())
        g.seed, g.system_prompt = self.g_seed.value(), self.g_system.toPlainText()
        self.ctx.store.save_later()

    def _toggle_params(self, on: bool) -> None:
        self.params.setVisible(on)
        self.ctx.store.s.show_params_panel = on
        self.ctx.store.save_later()

    # ---- server state --------------------------------------------------
    def _toggle_load(self) -> None:
        srv = self.ctx.server
        if srv.state in ("loading", "ready"):
            self._pending = False
            srv.unload()
        else:
            self._load_selected()

    def _load_selected(self) -> bool:
        e = self.current_entry()
        if not e:
            self.open_models.emit()
            return False
        self.ctx.server.load(e, self.ctx.store.s, self.ctx.hw)
        return True

    def _on_state(self, state: str) -> None:
        c = self.ctx.colors
        srv = self.ctx.server
        has_models = bool(self.ctx.store.s.models)
        names = {"unloaded": (tr("Not loaded"), c["muted"]), "loading": (tr("Loading…"), c["warn"]), "ready": (tr("Ready"), c["ok"])}
        text, color = names.get(state, names["unloaded"])
        if state == "ready" and srv.entry:
            text += " · " + srv.entry.name
        self.pill.setText(text)
        self.pill.setStyleSheet("background:%s; color:#ffffff; border-radius:10px; padding:3px 10px; font-weight:600;" % color)
        self.btn_load.setText({"unloaded": tr("Load model"), "loading": tr("Cancel"), "ready": tr("Unload")}.get(state, ""))
        self.btn_load.setEnabled(has_models)
        if state == "ready" and self._pending:
            self._pending = False
            QTimer.singleShot(0, self._generate)

    def _on_server_failed(self, message: str) -> None:
        self._pending = False
        if self.worker is None:
            b = self.view.add_bubble("assistant")
            b.set_error(message)

    # ---- chat ----------------------------------------------------------
    def set_chat(self, chat) -> None:
        self.stop_generation()
        self.chat = chat
        self.view.clear()
        for m in chat.messages:
            b = self.view.add_bubble(m["role"])
            b.set_content(m["content"], m.get("reasoning", ""))
            if m.get("stats"):
                b.set_meta(m["stats"])
        self.view.set_hint(tr("Pick a model, press “Load model” and start chatting.\nEverything runs locally on your computer."))

    def _save_chat(self) -> None:
        self.ctx.chats.save(self.chat)
        self.chat_changed.emit(self.chat)

    def on_send(self) -> None:
        if self.worker is not None:
            self.stop_generation()
            return
        text = self.input.toPlainText().strip()
        if not text or self.chat is None:
            return
        entry = self.current_entry()
        if not entry:
            self.open_models.emit()
            return
        self.input.clear()
        self.last_activity = time.time()
        self.chat.messages.append({"role": "user", "content": text})
        if len(self.chat.messages) == 1:
            self.chat.title = text.replace("\n", " ")[:40]
        self.view.add_bubble("user").set_content(text)
        self._save_chat()
        srv = self.ctx.server
        if srv.state == "ready" and srv.entry and srv.entry.id == entry.id:
            self._generate()
        else:
            self._pending = True
            if srv.state != "loading" or (srv.entry and srv.entry.id != entry.id):
                if not self._load_selected():
                    self._pending = False

    def _generate(self) -> None:
        srv = self.ctx.server
        if srv.state != "ready" or srv.entry is None or self.chat is None or self.worker is not None:
            return
        entry = srv.entry
        msgs = fit_messages(entry.gen.system_prompt, self.chat.messages, entry.load.n_ctx, entry.gen.max_tokens)
        self._buf, self._rbuf = "", ""
        self._bubble = self.view.add_bubble("assistant")
        self._bubble.set_content("")
        w = ChatWorker(srv.port, msgs, entry.gen, self)
        w.token.connect(self._on_token)
        w.reasoning.connect(self._on_reasoning)
        w.failed.connect(self._on_failed)
        w.done.connect(self._on_done)
        self.worker = w
        self.btn_send.setText(tr("Stop"))
        self.btn_regen.setEnabled(False)
        self._flush_timer.start()
        w.start()

    def _on_token(self, t: str) -> None:
        self._buf += t
        self.last_activity = time.time()

    def _on_reasoning(self, t: str) -> None:
        self._rbuf += t
        self.last_activity = time.time()

    def _flush(self) -> None:
        if self._bubble is not None:
            self._bubble.set_content(self._buf, self._rbuf)

    def _on_failed(self, msg: str) -> None:
        if self._bubble is not None:
            hint = ""
            if "context" in msg.lower():
                hint = "\n" + tr("Tip: increase the context size in Models, or start a new chat.")
            self._bubble.set_error(msg + hint)
        self._failed = True

    def _on_done(self, stats: dict) -> None:
        self._flush_timer.stop()
        failed = self._failed
        self._failed = False
        if self._bubble is not None and not failed:
            self._bubble.set_content(self._buf, self._rbuf)
            meta = ""
            if stats.get("tokens"):
                meta = "%d %s" % (stats["tokens"], tr("tokens"))
                if stats.get("tps"):
                    meta = "%.1f %s · %s" % (stats["tps"], tr("tok/s"), meta)
                meta += " · %.1f s" % stats["seconds"]
            self._bubble.set_meta(meta)
            if self._buf or self._rbuf:
                msg = {"role": "assistant", "content": self._buf}
                if self._rbuf:
                    msg["reasoning"] = self._rbuf
                if meta:
                    msg["stats"] = meta
                self.chat.messages.append(msg)
                self._save_chat()
            self.lbl_info.setText(meta)
        elif self._bubble is not None and not (self._buf or self._rbuf):
            pass
        if self.worker is not None:
            self.worker.deleteLater()
        self.worker = None
        self._bubble = None
        self.btn_send.setText(tr("Send"))
        self.btn_regen.setEnabled(True)
        self.last_activity = time.time()

    def stop_generation(self) -> None:
        self._pending = False
        if self.worker is not None:
            self.worker.stop()

    def on_regen(self) -> None:
        if self.worker is not None or self.chat is None or not self.chat.messages:
            return
        if self.chat.messages[-1]["role"] == "assistant":
            self.chat.messages.pop()
            self.view.remove_last()
            self._save_chat()
        if not self.chat.messages:
            return
        if self.ctx.server.state == "ready":
            self._generate()
        else:
            self._pending = True
            self._load_selected()

    def shutdown(self) -> None:
        if self.worker is not None:
            self.worker.stop()
            self.worker.wait(2000)
