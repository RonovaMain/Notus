"""Chat page: model / assistant / thinking bar, conversation, attachments and generation parameters."""
from __future__ import annotations

import os
import time

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                             QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from .. import assistants as assistants_mod
from ..attachments import AttachmentError, image_to_data_url, kind_of, qimage_to_data_url, read_document
from ..client import ChatWorker, approx_tokens, fit_messages, message_text, split_think
from ..config import vision_active
from ..i18n import tr
from .widgets import ChatView, SliderSpin

FILE_FILTER = ("Files (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.pdf *.docx *.txt *.md *.csv *.json *.xml *.yaml *.yml "
               "*.log *.py *.js *.ts *.java *.c *.cpp *.h *.cs *.go *.rs *.php *.sh *.sql *.html *.css);;All files (*)")


class _InputEdit(QPlainTextEdit):
    submitted = pyqtSignal()
    paths_pasted = pyqtSignal(list)
    image_pasted = pyqtSignal(object)

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.submitted.emit()
            return
        super().keyPressEvent(e)

    def canInsertFromMimeData(self, source) -> bool:
        return source.hasImage() or source.hasUrls() or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source) -> None:
        if source.hasUrls():
            files = [u.toLocalFile() for u in source.urls() if u.isLocalFile()]
            if files:
                self.paths_pasted.emit(files)
                return
        if source.hasImage():
            img = source.imageData()
            if isinstance(img, QImage) and not img.isNull():
                self.image_pasted.emit(img)
                return
        super().insertFromMimeData(source)


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
        self._failed = False
        self._loading_gen = False
        self._ctx_used = 0
        self.pending_files: list[dict] = []
        self.pending_images: list[str] = []
        self.last_activity = time.time()
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(50)
        self._flush_timer.timeout.connect(self._flush)
        self._build()
        QShortcut(QKeySequence("Escape"), self, activated=self.stop_generation)
        ctx.server.state_changed.connect(self._on_state)
        ctx.server.failed.connect(self._on_server_failed)
        self.refresh_models()
        self.refresh_assistants()
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
        self.model_combo.setMinimumWidth(220)
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        self.btn_load = QPushButton()
        self.btn_load.setObjectName("Primary")
        self.btn_load.clicked.connect(self._toggle_load)
        self.pill = QLabel()
        self.assistant_combo = QComboBox()
        self.assistant_combo.setMinimumWidth(150)
        self.assistant_combo.setToolTip(tr("Assistant: a ready-made role with its own instructions"))
        self.assistant_combo.currentIndexChanged.connect(self._on_assistant_changed)
        self.think_combo = QComboBox()
        for label, v in ((tr("Thinking: auto"), "auto"), (tr("Thinking: on"), "on"), (tr("Thinking: off"), "off")):
            self.think_combo.addItem(label, v)
        self.think_combo.setToolTip(tr("Switch the model's reasoning mode on or off (models without one ignore this)."))
        self.think_combo.currentIndexChanged.connect(self._on_think_changed)
        self.btn_log = QPushButton(tr("Log"))
        self.btn_log.clicked.connect(self.show_log.emit)
        self.btn_params = QPushButton(tr("Parameters"))
        self.btn_params.setCheckable(True)
        self.btn_params.setChecked(self.ctx.store.s.show_params_panel)
        self.btn_params.toggled.connect(self._toggle_params)
        for w in (self.model_combo, self.btn_load, self.pill, self.assistant_combo, self.think_combo):
            tl.addWidget(w)
        tl.addStretch(1)
        tl.addWidget(self.btn_log)
        tl.addWidget(self.btn_params)
        col.addWidget(top)

        self.view = ChatView(self.ctx.colors)
        self.view.set_hint(self._hint())
        col.addWidget(self.view, 1)

        bar = QFrame()
        bar.setObjectName("InputBar")
        bl = QVBoxLayout(bar)
        bl.setContentsMargins(16, 10, 16, 8)
        bl.setSpacing(6)
        self.chips = QWidget()
        self.chips_lay = QHBoxLayout(self.chips)
        self.chips_lay.setContentsMargins(0, 0, 0, 0)
        self.chips_lay.setSpacing(6)
        self.chips.hide()
        bl.addWidget(self.chips)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_attach = QPushButton("📎")
        self.btn_attach.setToolTip(tr("Attach images or documents (you can also paste or drag them in)"))
        self.btn_attach.clicked.connect(self.pick_files)
        self.input = _InputEdit()
        self.input.setPlaceholderText(tr("Message Notus…  (Enter — send, Shift+Enter — new line)"))
        self.input.setFixedHeight(66)
        self.input.submitted.connect(self.on_send)
        self.input.paths_pasted.connect(self.attach_paths)
        self.input.image_pasted.connect(self.attach_qimage)
        self.btn_send = QPushButton(tr("Send"))
        self.btn_send.setObjectName("Primary")
        self.btn_send.setMinimumWidth(96)
        self.btn_send.clicked.connect(self.on_send)
        self.btn_regen = QPushButton("↻")
        self.btn_regen.setToolTip(tr("Regenerate the last answer"))
        self.btn_regen.clicked.connect(self.on_regen)
        row.addWidget(self.btn_attach, 0, Qt.AlignmentFlag.AlignBottom)
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

    def _hint(self) -> str:
        return tr("Pick a model, press “Load model” and start chatting.\nEverything runs locally on your computer.")

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
        add(tr("System prompt"), self.g_system, tr("An assistant with its own instructions replaces this text."))
        lay.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        for w in (self.g_temp, self.g_top_p, self.g_top_k, self.g_min_p, self.g_rep, self.g_max):
            w.valueChanged.connect(self._gen_changed)
        self.g_seed.valueChanged.connect(self._gen_changed)
        self.g_system.textChanged.connect(self._gen_changed)
        return panel

    # ---- models / assistants / thinking --------------------------------
    def current_entry(self):
        return self.ctx.store.get_model(self.model_combo.currentData())

    def current_assistant(self):
        if not self.ctx.store.s.mod_assistants:
            return None
        return self.ctx.store.get_assistant(self.assistant_combo.currentData())

    def apply_modules(self) -> None:
        s = self.ctx.store.s
        self.assistant_combo.setVisible(s.mod_assistants)
        self.think_combo.setVisible(s.mod_thinking)
        self.btn_attach.setVisible(s.mod_files)
        if not s.mod_files:
            self.pending_files, self.pending_images = [], []
            self._refresh_chips()
        self._refresh_think_combo()

    def refresh_models(self) -> None:
        s = self.ctx.store.s
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for m in s.models:
            self.model_combo.addItem(m.name, m.id)
        if not s.models:
            self.model_combo.addItem(tr("No models — add one in “Models”"), "")
        self.model_combo.setCurrentIndex(max(0, self.model_combo.findData(s.last_model_id)))
        self.model_combo.blockSignals(False)
        self._on_model_changed()

    def refresh_assistants(self) -> None:
        s = self.ctx.store.s
        self.assistant_combo.blockSignals(True)
        self.assistant_combo.clear()
        self.assistant_combo.addItem(tr("No assistant"), "")
        for a in s.assistants:
            self.assistant_combo.addItem(a.name, a.id)
        self.assistant_combo.setCurrentIndex(max(0, self.assistant_combo.findData(s.last_assistant_id)))
        self.assistant_combo.blockSignals(False)
        self._refresh_think_combo()

    def _on_assistant_changed(self) -> None:
        self.ctx.store.s.last_assistant_id = self.assistant_combo.currentData() or ""
        self.ctx.store.save_later()
        self._refresh_think_combo()

    def _refresh_think_combo(self) -> None:
        """Thinking mode comes from the assistant if it overrides it, otherwise from the model's settings."""
        a, e = self.current_assistant(), self.current_entry()
        forced = a is not None and a.think != "inherit"
        value = a.think if forced else (e.gen.think if e else "auto")
        self.think_combo.blockSignals(True)
        self.think_combo.setCurrentIndex(max(0, self.think_combo.findData(value)))
        self.think_combo.setEnabled(not forced)
        self.think_combo.setToolTip(tr("This assistant sets the thinking mode itself.") if forced else
                                    tr("Switch the model's reasoning mode on or off (models without one ignore this)."))
        self.think_combo.blockSignals(False)

    def _on_think_changed(self) -> None:
        e = self.current_entry()
        if e:
            e.gen.think = self.think_combo.currentData() or "auto"
            self.ctx.store.save_later()

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
        self._refresh_think_combo()
        self._on_state(self.ctx.server.state)
        self._update_ctx()

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
        names = {"unloaded": (tr("Not loaded"), c["muted"]), "loading": (tr("Loading…"), c["warn"]), "ready": (tr("Ready"), c["ok"])}
        text, color = names.get(state, names["unloaded"])
        if state == "ready" and srv.entry:
            text += " · " + srv.entry.name
        self.pill.setText(text)
        self.pill.setStyleSheet("background:%s; color:#ffffff; border-radius:10px; padding:3px 10px; font-weight:600;" % color)
        self.btn_load.setText({"unloaded": tr("Load model"), "loading": tr("Cancel"), "ready": tr("Unload")}.get(state, ""))
        self.btn_load.setEnabled(bool(self.ctx.store.s.models))
        if state == "ready" and self._pending:
            self._pending = False
            QTimer.singleShot(0, self._generate)

    def _on_server_failed(self, message: str) -> None:
        self._pending = False
        if self.worker is None:
            self.view.add_bubble("assistant").set_error(message)

    # ---- attachments ---------------------------------------------------
    def _vision_ok(self) -> bool:
        return vision_active(self.current_entry(), self.ctx.store.s)

    def _max_file_chars(self) -> int:
        e = self.current_entry()
        n_ctx = e.load.n_ctx if e else 4096
        reply = e.gen.max_tokens if e else 1024
        return max(2000, int((n_ctx - reply - 600) * 3 * 0.7))

    def pick_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, tr("Attach files"), "", FILE_FILTER)
        self.attach_paths(files)

    def attach_paths(self, files: list) -> None:
        if not self.ctx.store.s.mod_files:
            return
        problems = []
        for f in files:
            name = os.path.basename(f)
            kind = kind_of(f)
            try:
                if kind == "image":
                    if not self._vision_ok():
                        problems.append("%s: %s" % (name, tr("images are off: enable vision for this model in “Models” (and in Settings → Modules)")))
                        continue
                    self.pending_images.append(image_to_data_url(f))
                elif kind == "file":
                    text, truncated = read_document(f, self._max_file_chars())
                    self.pending_files.append({"name": name, "text": text, "truncated": truncated})
                    if truncated:
                        problems.append("%s: %s" % (name, tr("too long for the context, only the beginning is used")))
                else:
                    problems.append("%s: %s" % (name, tr("unsupported file type")))
            except AttachmentError as e:
                problems.append("%s: %s" % (name, e))
        self._refresh_chips()
        if problems:
            self.lbl_info.setText("⚠ " + " · ".join(problems))

    def attach_qimage(self, img) -> None:
        if not self.ctx.store.s.mod_files:
            return
        if not self._vision_ok():
            self.lbl_info.setText("⚠ " + tr("images are off: enable vision for this model in “Models” (and in Settings → Modules)"))
            return
        self.pending_images.append(qimage_to_data_url(img))
        self._refresh_chips()

    def _refresh_chips(self) -> None:
        while self.chips_lay.count():
            w = self.chips_lay.takeAt(0).widget()
            if w is not None:
                w.setParent(None)

        def chip(text: str, remove) -> None:
            b = QPushButton(text + "  ✕")
            b.setObjectName("Chip")
            b.setToolTip(tr("Remove"))
            b.clicked.connect(remove)
            self.chips_lay.addWidget(b)

        for i, f in enumerate(self.pending_files):
            chip("📎 " + f["name"], lambda _=False, i=i: self._drop(self.pending_files, i))
        for i in range(len(self.pending_images)):
            chip("🖼 " + tr("image") + " %d" % (i + 1), lambda _=False, i=i: self._drop(self.pending_images, i))
        self.chips_lay.addStretch(1)
        self.chips.setVisible(bool(self.pending_files or self.pending_images))

    def _drop(self, lst: list, i: int) -> None:
        del lst[i]
        self._refresh_chips()

    # ---- chat ----------------------------------------------------------
    def set_chat(self, chat) -> None:
        self.stop_generation()
        self.chat = chat
        self.view.clear()
        show = self.ctx.store.s.show_thinking
        for m in chat.messages:
            b = self.view.add_bubble(m["role"])
            b.set_attachments(m.get("files"), m.get("images"))
            b.set_content(m["content"], m.get("reasoning", ""), show)
            if m.get("stats"):
                b.set_meta(m["stats"])
        self.view.set_hint(self._hint())
        self._ctx_used = 0
        self._update_ctx()

    def _save_chat(self) -> None:
        self.ctx.chats.save(self.chat)
        self.chat_changed.emit(self.chat)

    def _update_ctx(self) -> None:
        e = self.ctx.server.entry if self.ctx.server.state != "unloaded" and self.ctx.server.entry else self.current_entry()
        if not e or self.chat is None:
            return
        used = self._ctx_used or sum(approx_tokens(message_text(m)) for m in self.chat.messages)
        total = e.load.n_ctx
        txt = tr("Context") + ": ~%s / %s" % (_k(used), _k(total))
        self.lbl_info.setText(txt if used / max(total, 1) < 0.85 else "⚠ " + txt + " — " + tr("almost full, old messages will be dropped"))

    def on_send(self) -> None:
        if self.worker is not None:
            self.stop_generation()
            return
        text = self.input.toPlainText().strip()
        if (not text and not self.pending_files and not self.pending_images) or self.chat is None:
            return
        entry = self.current_entry()
        if not entry:
            self.open_models.emit()
            return
        self.input.clear()
        self.last_activity = time.time()
        msg = {"role": "user", "content": text}
        if self.pending_files:
            msg["files"] = self.pending_files
        if self.pending_images:
            msg["images"] = self.pending_images
        self.pending_files, self.pending_images = [], []
        self._refresh_chips()
        self.chat.messages.append(msg)
        if len(self.chat.messages) == 1:
            self.chat.title = (text or (msg.get("files") or [{"name": tr("Attachment")}])[0]["name"]).replace("\n", " ")[:40]
        b = self.view.add_bubble("user")
        b.set_attachments(msg.get("files"), msg.get("images"))
        b.set_content(text)
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
        gen, think = assistants_mod.resolve(entry.gen, self.current_assistant())
        if not self.ctx.store.s.mod_thinking:
            think = "auto"
        s = self.ctx.store.s
        vision = vision_active(entry, s) and srv.vision_loaded
        msgs = fit_messages(gen.system_prompt, self.chat.messages, entry.load.n_ctx, gen.max_tokens, vision)
        self._buf, self._rbuf, self._failed = "", "", False
        self._bubble = self.view.add_bubble("assistant")
        self._bubble.set_content("")
        w = ChatWorker(srv.port, msgs, gen, think, self)
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

    def _split(self) -> tuple[str, str]:
        """(answer, reasoning) - handles both reasoning_content and inline <think> tags."""
        inline, text = split_think(self._buf)
        reasoning = self._rbuf + (("\n" if self._rbuf and inline else "") + inline)
        return text, reasoning

    def _flush(self) -> None:
        if self._bubble is not None:
            text, reasoning = self._split()
            self._bubble.set_content(text, reasoning, self.ctx.store.s.show_thinking)

    def _on_failed(self, msg: str) -> None:
        self._failed = True
        if self._bubble is not None:
            hint = ""
            if "context" in msg.lower():
                hint = "\n" + tr("Tip: increase the context size in Models, or start a new chat.")
            self._bubble.set_error(msg + hint)

    def _on_done(self, stats: dict) -> None:
        self._flush_timer.stop()
        if self._bubble is not None and not self._failed:
            text, reasoning = self._split()
            self._bubble.set_content(text, reasoning, self.ctx.store.s.show_thinking)
            meta = ""
            if stats.get("tokens"):
                meta = "%d %s" % (stats["tokens"], tr("tokens"))
                if stats.get("tps"):
                    meta = "%.1f %s · %s" % (stats["tps"], tr("tok/s"), meta)
                meta += " · %.1f s" % stats["seconds"]
            self._bubble.set_meta(meta)
            if text or reasoning:
                msg = {"role": "assistant", "content": text}
                if reasoning:
                    msg["reasoning"] = reasoning
                if meta:
                    msg["stats"] = meta
                self.chat.messages.append(msg)
                self._save_chat()
            used = stats.get("prompt_n", 0) + stats.get("cache_n", 0) + stats.get("tokens", 0)
            self._ctx_used = used if used else 0
        if self.worker is not None:
            self.worker.deleteLater()
        self.worker = None
        self._bubble = None
        self.btn_send.setText(tr("Send"))
        self.btn_regen.setEnabled(True)
        self.last_activity = time.time()
        self._update_ctx()

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


def _k(n: int) -> str:
    return "%.1fk" % (n / 1000) if n >= 1000 else str(n)
