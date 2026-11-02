"""Persistent settings + model library (JSON in the data directory)."""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from . import paths
from .config import AppSettings, Assistant, ModelEntry, from_dict


def _norm(p: str) -> str:
    try:
        return os.path.normcase(str(Path(p).resolve()))
    except OSError:
        return os.path.normcase(p)


class Store(QObject):
    models_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.path = paths.data_dir() / "settings.json"
        self.s = AppSettings()
        self._timer: QTimer | None = None

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raw = {}
        except (OSError, ValueError):
            raw = {}
        models = [ModelEntry.from_dict(m) for m in raw.pop("models", []) if isinstance(m, dict)]
        assistants = [Assistant.from_dict(a) for a in raw.pop("assistants", []) if isinstance(a, dict)]
        self.s = from_dict(AppSettings, raw)
        self.s.models = [m for m in models if m.path]
        self.s.assistants = [a for a in assistants if a.name]

    def save(self) -> None:
        data = asdict(self.s)
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass

    def save_later(self, ms: int = 600) -> None:
        if self._timer is None:
            self._timer = QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.timeout.connect(self.save)
        self._timer.start(ms)

    # ---- model library -------------------------------------------------
    def get_assistant(self, assistant_id):
        for a in self.s.assistants:
            if a.id == assistant_id:
                return a
        return None

    def get_model(self, model_id) -> ModelEntry | None:
        for m in self.s.models:
            if m.id == model_id:
                return m
        return None

    def has_path(self, path: str) -> bool:
        n = _norm(path)
        return any(_norm(m.path) == n for m in self.s.models)

    def add_entry(self, entry: ModelEntry) -> bool:
        if self.has_path(entry.path):
            return False
        self.s.models.append(entry)
        self.save_later()
        self.models_changed.emit()
        return True

    def remove_model(self, model_id: str) -> None:
        self.s.models = [m for m in self.s.models if m.id != model_id]
        if self.s.last_model_id == model_id:
            self.s.last_model_id = self.s.models[0].id if self.s.models else ""
        self.save_later()
        self.models_changed.emit()
