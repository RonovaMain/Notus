"""Main window: sidebar (chats + navigation), pages and status bar."""
from __future__ import annotations

import time
from collections import deque

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
                             QMenu, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from .. import APP_NAME, __version__, paths
from ..backend import ServerManager
from ..chats import ChatStore
from ..context import AppContext
from ..hardware import detect_hardware
from ..i18n import tr
from ..monitor import DeviceProbe, StatsPoller
from .about_page import AboutPage
from .chat_page import ChatPage
from .dialogs import LogDialog
from .models_page import ModelsPage
from .settings_page import SettingsPage


class MainWindow(QMainWindow):
    def __init__(self, store, colors: dict) -> None:
        super().__init__()
        self.store = store
        self.setWindowTitle(APP_NAME)
        self.resize(1320, 840)
        self.setMinimumSize(1000, 660)
        self.setAcceptDrops(True)
        hw = detect_hardware()
        self.server = ServerManager(self)
        self.chats = ChatStore()
        self.ctx = AppContext(store, self.server, self.chats, hw, colors)
        self.log = deque(maxlen=4000)
        self.log_dialog: LogDialog | None = None
        self._chat_list = self.chats.list_all()
        self._build()
        self.server.log_line.connect(self._on_log)
        self.server.failed.connect(self._on_failed)
        self.server.state_changed.connect(self._on_state)
        store.models_changed.connect(self.chat_page.refresh_models)
        self.poller = StatsPoller(hw, self)
        self.poller.updated.connect(self._on_stats)
        self.poller.start()
        self._probe = None
        self.refresh_devices()
        self.idle_timer = QTimer(self)
        self.idle_timer.timeout.connect(self._check_idle)
        self.idle_timer.start(30000)
        if self._chat_list:
            self._open_chat(self._chat_list[0].id)
        else:
            self.new_chat()

    # ---- construction --------------------------------------------------
    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(250)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(14, 16, 14, 12)
        sl.setSpacing(8)
        brand = QHBoxLayout()
        logo = QLabel()
        pm = QPixmap(str(paths.asset("icon.png")))
        if not pm.isNull():
            logo.setPixmap(pm.scaled(34, 34, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        name = QLabel("NOTUS")
        name.setObjectName("Brand")
        brand.addWidget(logo)
        brand.addWidget(name)
        brand.addStretch(1)
        sl.addLayout(brand)
        sl.addSpacing(6)
        self.btn_new = QPushButton("+  " + tr("New chat"))
        self.btn_new.setObjectName("Primary")
        self.btn_new.clicked.connect(self.new_chat)
        sl.addWidget(self.btn_new)
        self.chat_list = QListWidget()
        self.chat_list.currentItemChanged.connect(self._on_chat_item)
        self.chat_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.chat_list.customContextMenuRequested.connect(self._chat_menu)
        sl.addWidget(self.chat_list, 1)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons = []
        for i, text in enumerate((tr("Chat"), tr("Models"), tr("Settings"), tr("About"))):
            b = QPushButton(text)
            b.setObjectName("Nav")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, idx=i: self.show_page(idx))
            self.nav_group.addButton(b)
            self.nav_buttons.append(b)
            sl.addWidget(b)
        ver = QLabel("v%s" % __version__)
        ver.setObjectName("Muted")
        sl.addWidget(ver)
        h.addWidget(side)

        self.stack = QStackedWidget()
        self.chat_page = ChatPage(self.ctx)
        self.models_page = ModelsPage(self.ctx)
        self.settings_page = SettingsPage(self.ctx)
        self.about_page = AboutPage(self.ctx)
        for p in (self.chat_page, self.models_page, self.settings_page, self.about_page):
            self.stack.addWidget(p)
        h.addWidget(self.stack, 1)
        self.chat_page.chat_changed.connect(self._on_chat_changed)
        self.chat_page.open_models.connect(lambda: self.show_page(1))
        self.chat_page.show_log.connect(self.open_log)
        self.models_page.load_requested.connect(self._load_from_models)
        self.settings_page.theme_changed.connect(self._on_theme)
        self.settings_page.devices_requested.connect(self.refresh_devices)

        self.lbl_state = QLabel("")
        self.lbl_ram = QLabel("")
        self.lbl_gpu = QLabel("")
        self.lbl_be = QLabel("")
        sb = self.statusBar()
        sb.setSizeGripEnabled(False)
        sb.addWidget(self.lbl_state)
        for w in (self.lbl_be, self.lbl_ram, self.lbl_gpu):
            sb.addPermanentWidget(w)
        self.show_page(0)

    def show_page(self, idx: int) -> None:
        self.stack.setCurrentIndex(idx)
        self.nav_buttons[idx].setChecked(True)
        if idx == 1:
            self.models_page.on_show()
        elif idx == 2:
            self.settings_page.refresh_hw()

    # ---- chats ---------------------------------------------------------
    def _refresh_chat_list(self, select_id: str | None = None) -> None:
        self.chat_list.blockSignals(True)
        self.chat_list.clear()
        for c in self._chat_list:
            it = QListWidgetItem(c.title or tr("New chat"))
            it.setData(Qt.ItemDataRole.UserRole, c.id)
            self.chat_list.addItem(it)
            if c.id == select_id:
                self.chat_list.setCurrentItem(it)
        self.chat_list.blockSignals(False)

    def new_chat(self) -> None:
        cur = self.chat_page.chat
        if cur is not None and not cur.messages:
            self.show_page(0)
            return
        c = self.chats.new(tr("New chat"))
        self._chat_list.insert(0, c)
        self._refresh_chat_list(c.id)
        self.chat_page.set_chat(c)
        self.show_page(0)

    def _open_chat(self, chat_id: str) -> None:
        for c in self._chat_list:
            if c.id == chat_id:
                self._refresh_chat_list(chat_id)
                self.chat_page.set_chat(c)
                self.show_page(0)
                return

    def _on_chat_item(self, item, _prev) -> None:
        if item is not None:
            self._open_chat(item.data(Qt.ItemDataRole.UserRole))

    def _on_chat_changed(self, chat) -> None:
        if chat in self._chat_list:
            self._chat_list.remove(chat)
        self._chat_list.insert(0, chat)
        self._refresh_chat_list(chat.id)

    def _chat_menu(self, pos) -> None:
        item = self.chat_list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        act = menu.addAction(tr("Delete chat"))
        if menu.exec(self.chat_list.mapToGlobal(pos)) is act:
            cid = item.data(Qt.ItemDataRole.UserRole)
            was_current = self.chat_page.chat is not None and self.chat_page.chat.id == cid
            self.chats.delete(cid)
            self._chat_list = [c for c in self._chat_list if c.id != cid]
            self._refresh_chat_list()
            if was_current:
                self.chat_page.chat = None
                if self._chat_list:
                    self._open_chat(self._chat_list[0].id)
                else:
                    self.new_chat()

    # ---- backend events ------------------------------------------------
    def _load_from_models(self, model_id: str) -> None:
        e = self.store.get_model(model_id)
        if e:
            self.show_page(0)
            self.chat_page.refresh_models()
            self.server.load(e, self.store.s, self.ctx.hw)

    def _on_log(self, line: str) -> None:
        self.log.append(line)
        if self.log_dialog is not None:
            self.log_dialog.append(line)

    def open_log(self) -> None:
        if self.log_dialog is None:
            self.log_dialog = LogDialog(list(self.log), self)
            self.log_dialog.finished.connect(lambda _=0: setattr(self, "log_dialog", None))
        self.log_dialog.show()
        self.log_dialog.raise_()

    def _on_failed(self, message: str) -> None:
        self.lbl_state.setText(message.splitlines()[0] if message else "")

    def _on_state(self, state: str) -> None:
        self.poller.pid = self.server.pid if state != "unloaded" else 0
        if state == "unloaded":
            self.refresh_devices()          # free VRAM changed after unloading
        e = self.server.entry
        self.lbl_state.setText({"unloaded": tr("Model unloaded — memory is free"),
                                "loading": tr("Loading {name}…").format(name=e.name if e else ""),
                                "ready": tr("{name} is ready").format(name=e.name if e else "")}[state])

    def _on_stats(self, hw, rss_mb: int) -> None:
        self.ctx.hw = hw
        self.lbl_ram.setText("RAM %.1f / %.1f GB" % ((hw.ram_total_mb - hw.ram_free_mb) / 1024, hw.ram_total_mb / 1024))
        if hw.gpus:
            g = hw.gpus[0]
            self.lbl_gpu.setText("VRAM %.1f / %.1f GB" % (g.used_mb / 1024, g.total_mb / 1024))
        else:
            self.lbl_gpu.setText("")
        self.lbl_be.setText((tr("Backend") + " %.1f GB" % (rss_mb / 1024)) if rss_mb else "")

    def refresh_devices(self) -> None:
        if self._probe is not None and self._probe.isRunning():
            return
        self._probe = DeviceProbe(self.store.s.backend_dir, self)
        self._probe.found.connect(self._on_devices)
        self._probe.start()

    def _on_devices(self, devices: list) -> None:
        self.ctx.devices = devices
        self.settings_page.populate_devices()
        self.settings_page.refresh_hw()
        if self.stack.currentIndex() == 1:
            self.models_page.on_show()

    def _check_idle(self) -> None:
        minutes = self.store.s.auto_unload_minutes
        cp = self.chat_page
        if minutes > 0 and self.server.state == "ready" and cp.worker is None and time.time() - cp.last_activity > minutes * 60:
            self.server.unload()

    def _on_theme(self, colors: dict) -> None:
        self.ctx.colors = colors
        self.chat_page.view.c = colors

    # ---- drag & drop ---------------------------------------------------
    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls() and any(u.toLocalFile().lower().endswith(".gguf") for u in e.mimeData().urls()):
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        files = [u.toLocalFile() for u in e.mimeData().urls() if u.toLocalFile().lower().endswith(".gguf")]
        self.show_page(1)
        self.models_page.add_paths(files)

    # ---- shutdown ------------------------------------------------------
    def closeEvent(self, e) -> None:
        self.poller.stop()
        if self._probe is not None:
            self._probe.wait(5000)
        self.chat_page.shutdown()
        self.server.unload()
        self.poller.wait(3000)
        self.store.save()
        super().closeEvent(e)
