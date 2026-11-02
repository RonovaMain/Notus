"""Built-in assistants (personas) and helpers to combine them with model settings."""
from __future__ import annotations

import dataclasses
import uuid

from .config import Assistant, GenSettings
from .i18n import tr

_LANG = " Reply in the language of the user's message."

# (key, English name, system prompt, temperature, thinking)
BUILTINS = [
    ("general", "General assistant",
     "You are a helpful, honest and concise assistant." + _LANG, -1.0, "inherit"),
    ("coder", "Programmer",
     "You are an expert software engineer. Give correct, idiomatic code in fenced code blocks, explain only what is "
     "necessary, mention edge cases and point out bugs you notice." + _LANG, 0.3, "inherit"),
    ("translator", "Translator (RU ↔ EN)",
     "You are a professional translator. If the text is in Russian, translate it into English; otherwise translate it "
     "into Russian. Keep the tone, formatting and meaning. Output only the translation.", 0.2, "off"),
    ("analyst", "Document analyst",
     "You analyse documents the user attaches. First give a short structured summary and the key points, then answer "
     "questions using only the document. If the answer is not in the document, say so." + _LANG, 0.3, "inherit"),
    ("editor", "Text editor",
     "You are a careful editor. Fix grammar, spelling and style while preserving the author's meaning and voice. "
     "Return the corrected text first, then a short list of the main changes." + _LANG, 0.4, "off"),
    ("vision", "Image describer / OCR",
     "You look at images the user sends. Describe what is visible, transcribe any text exactly as it appears, and for "
     "screenshots explain the interface and what is happening. Be factual; do not guess what you cannot see." + _LANG,
     0.2, "off"),
    ("teacher", "Teacher",
     "You are a patient teacher. Explain step by step in simple words, give a small example, and check understanding "
     "with one short question at the end." + _LANG, 0.6, "inherit"),
]


def make_builtin(key: str) -> Assistant | None:
    for k, name, prompt, temp, think in BUILTINS:
        if k == key:
            return Assistant(id=uuid.uuid4().hex[:12], name=tr(name), system_prompt=prompt,
                             temperature=temp, think=think, builtin_key=k)
    return None


def ensure_seeded(store) -> None:
    """First run: add the shipped assistants. Later runs never re-add what the user deleted."""
    if store.s.assistants_seeded:
        return
    store.s.assistants = [make_builtin(k) for k, *_ in BUILTINS] + list(store.s.assistants)
    store.s.assistants_seeded = True
    store.save()


def restore_missing(store) -> int:
    have = {a.builtin_key for a in store.s.assistants if a.builtin_key}
    added = 0
    for k, *_ in BUILTINS:
        if k not in have:
            store.s.assistants.append(make_builtin(k))
            added += 1
    return added


def resolve(gen: GenSettings, assistant: Assistant | None) -> tuple[GenSettings, str]:
    """Effective generation settings and thinking mode for a request."""
    g = dataclasses.replace(gen)
    think = gen.think
    if assistant is not None:
        if assistant.system_prompt.strip():
            g.system_prompt = assistant.system_prompt
        if assistant.temperature >= 0:
            g.temperature = assistant.temperature
        if assistant.think != "inherit":
            think = assistant.think
    return g, think
