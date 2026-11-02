"""Background poller for RAM / VRAM / backend memory usage."""
from __future__ import annotations

import psutil
from PyQt6.QtCore import QThread, pyqtSignal

from . import paths
from .backend import list_devices
from .hardware import Hardware, snapshot


class StatsPoller(QThread):
    updated = pyqtSignal(object, int)       # Hardware snapshot, backend RSS in MB

    def __init__(self, static_hw: Hardware, parent=None) -> None:
        super().__init__(parent)
        self.static = static_hw
        self.pid = 0
        self.enabled = True
        self._run = True

    def stop(self) -> None:
        self._run = False

    def run(self) -> None:
        while self._run:
            try:
                if not self.enabled:
                    raise RuntimeError("monitor off")
                hw = snapshot(self.static)
                rss = 0
                if self.pid:
                    try:
                        rss = psutil.Process(self.pid).memory_info().rss // 1048576
                    except psutil.Error:
                        rss = 0
                self.updated.emit(hw, int(rss))
            except Exception:
                pass
            for _ in range(25):
                if not self._run:
                    return
                self.msleep(100)


class DeviceProbe(QThread):
    """Asks the backend which compute devices it can see (takes a second or two)."""
    found = pyqtSignal(list)

    def __init__(self, backend_dir: str, parent=None) -> None:
        super().__init__(parent)
        self.backend_dir = backend_dir

    def run(self) -> None:
        exe = paths.find_backend_exe("llama-server", self.backend_dir)
        self.found.emit(list_devices(exe) if exe else [])
