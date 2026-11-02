"""Chat history: one JSON file per conversation."""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field

from . import paths
from .config import from_dict


@dataclass
class Chat:
    id: str
    title: str = ""
    updated: float = 0.0
    # messages: {"role": "user"|"assistant", "content": str, "reasoning"?: str, "stats"?: str}
    messages: list = field(default_factory=list)


class ChatStore:
    def __init__(self) -> None:
        self.dir = paths.chats_dir()

    def list_all(self) -> list[Chat]:
        chats = []
        for f in self.dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                chats.append(from_dict(Chat, data))
            except (OSError, ValueError, TypeError):
                continue
        chats.sort(key=lambda c: c.updated, reverse=True)
        return chats

    def new(self, title: str) -> Chat:
        return Chat(id=uuid.uuid4().hex[:12], title=title, updated=time.time())

    def save(self, chat: Chat) -> None:
        chat.updated = time.time()
        tmp = self.dir / f"{chat.id}.tmp"
        try:
            tmp.write_text(json.dumps(asdict(chat), ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.dir / f"{chat.id}.json")
        except OSError:
            pass

    def delete(self, chat_id: str) -> None:
        try:
            (self.dir / f"{chat_id}.json").unlink()
        except OSError:
            pass


def export_markdown(chat: Chat, path: str, user_label: str = "You", bot_label: str = "Notus") -> None:
    lines = ["# " + (chat.title or "Chat"), ""]
    for m in chat.messages:
        who = user_label if m["role"] == "user" else bot_label
        lines.append("**%s:**" % who)
        lines.append("")
        for f in m.get("files") or []:
            lines.append("*(attached: %s)*" % f.get("name", "file"))
        if m.get("images"):
            lines.append("*(%d image(s) attached)*" % len(m["images"]))
        lines.append(m.get("content", ""))
        lines += ["", "---", ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
