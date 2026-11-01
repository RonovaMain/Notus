"""Tiny translation layer: English source strings are the keys."""
from __future__ import annotations

from .i18n_ru import RU

_lang = "en"


def set_language(code: str) -> None:
    global _lang
    _lang = code if code in ("en", "ru") else "en"


def tr(text: str) -> str:
    return RU.get(text, text) if _lang == "ru" else text
