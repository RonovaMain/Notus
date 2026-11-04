"""Glue between the Qt application and the sharing gateway (runs the gateway, switches models on request)."""
from __future__ import annotations

import ipaddress
import socket
import threading
import time

import psutil
from PyQt6.QtCore import QObject, pyqtSignal

from . import __version__
from .config import image_cap, image_side, vision_active
from .gateway import Controller, Gateway


def lan_addresses() -> list[tuple[str, str]]:
    """[(interface, ipv4)] of this computer, private networks first."""
    out = []
    try:
        for iface, addrs in psutil.net_if_addrs().items():
            for a in addrs:
                if a.family != socket.AF_INET:
                    continue
                ip = ipaddress.ip_address(a.address)
                if ip.is_loopback or ip.is_link_local:
                    continue
                out.append((iface, a.address, ip.is_private))
    except Exception:
        return []
    out.sort(key=lambda x: not x[2])
    return [(i, a) for i, a, _ in out]


class ShareController(QObject, Controller):
    load_requested = pyqtSignal(str)
    unload_requested = pyqtSignal()
    status_changed = pyqtSignal()

    def __init__(self, ctx, parent=None) -> None:
        QObject.__init__(self, parent)
        self.ctx = ctx
        self.gw: Gateway | None = None
        self.error = ""
        self.api_activity = 0.0
        self._lock = threading.Lock()
        self._fail_seq = 0
        self._fail_msg = ""
        self.load_requested.connect(self._do_load)
        self.unload_requested.connect(ctx.server.unload)
        ctx.server.failed.connect(self._on_failed)

    # ---- main-thread slots ---------------------------------------------
    def _do_load(self, model_id: str) -> None:
        entry = self.ctx.store.get_model(model_id)
        if entry is not None:
            self.ctx.server.load(entry, self.ctx.store.s, self.ctx.hw)

    def _on_failed(self, message: str) -> None:
        self._fail_msg = message.strip().splitlines()[0] if message.strip() else "The model failed to load."
        self._fail_seq += 1

    def apply(self) -> None:
        """(Re)start the gateway according to the saved settings."""
        self.stop()
        s = self.ctx.store.s
        self.error = ""
        if not (s.share_enabled and s.mod_share):
            self.status_changed.emit()
            return
        if s.share_port == s.port:
            self.error = "The sharing port must differ from the internal backend port."
            self.status_changed.emit()
            return
        gw = Gateway(self, "0.0.0.0" if s.share_lan else "127.0.0.1", s.share_port, s.share_key,
                     s.share_allow_switch, s.share_autoload, s.share_webui, __version__)
        try:
            gw.start()
            self.gw = gw
        except OSError as e:
            self.error = "Cannot use port %d: %s" % (s.share_port, e)
        self.status_changed.emit()

    def stop(self) -> None:
        if self.gw is not None:
            self.gw.stop()
            self.gw = None

    # ---- Controller (called from gateway threads) ----------------------
    def info(self) -> dict:
        s, srv = self.ctx.store.s, self.ctx.server
        cur = srv.entry if srv.state != "unloaded" else None
        ready = srv.state == "ready"
        models = [{"id": m.id, "name": m.name, "loaded": bool(ready and cur and cur.id == m.id), "vision": bool(vision_active(m, s) and cur is not None and cur.id == m.id and srv.vision_loaded)}
                  for m in list(s.models)]
        assistants = [] if not s.mod_assistants else [{"id": a.id, "name": a.name, "system_prompt": a.system_prompt, "temperature": a.temperature,
                       "think": a.think} for a in list(s.assistants)]
        side = image_side(image_cap(cur.load, srv._vram)) if cur is not None else 768
        return {"state": srv.state, "loaded": cur.name if (ready and cur) else None, "models": models,
                "assistants": assistants, "image_side": side}

    def _find(self, requested):
        if not requested:
            return None
        key = str(requested).strip().lower()
        for m in list(self.ctx.store.s.models):
            if m.id.lower() == key or m.name.lower() == key:
                return m
        return None

    def ensure_model(self, requested, allow_switch: bool, autoload: bool, timeout: float):
        srv, store = self.ctx.server, self.ctx.store
        with self._lock:
            entry = self._find(requested)
            cur = srv.entry if srv.state in ("loading", "ready") else None
            if cur is None:
                if not autoload:
                    return None, "No model is loaded in Notus (automatic loading is switched off)."
                models = list(store.s.models)
                target = entry or store.get_model(store.s.last_model_id) or (models[0] if models else None)
                if target is None:
                    return None, "The Notus model library is empty."
            elif entry is not None and entry.id != cur.id and allow_switch:
                target = entry
            else:
                target = cur
            need_load = cur is None or target.id != cur.id
            seq = self._fail_seq
            if need_load:
                self.load_requested.emit(target.id)
            deadline = time.time() + timeout
            seen_loading = not need_load
            while time.time() < deadline:
                if srv.state == "ready" and srv.entry is not None and srv.entry.id == target.id:
                    return srv.port, ""
                if self._fail_seq != seq:
                    return None, self._fail_msg
                if srv.state == "loading":
                    seen_loading = True
                elif srv.state == "unloaded" and seen_loading:
                    return None, "The model was unloaded."
                time.sleep(0.25)
            return None, "Timed out while loading the model."

    def unload_model(self) -> None:
        self.unload_requested.emit()
        for _ in range(40):
            if self.ctx.server.state == "unloaded":
                break
            time.sleep(0.25)

    def touch(self) -> None:
        self.api_activity = time.time()
