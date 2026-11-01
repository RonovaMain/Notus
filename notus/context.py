"""Shared application state handed to every page."""
from __future__ import annotations


class AppContext:
    def __init__(self, store, server, chats, hw, colors) -> None:
        self.store = store
        self.server = server
        self.chats = chats
        self.hw = hw                          # latest hardware snapshot
        self.colors = colors                  # theme colour tokens
        self.devices: list = []               # GPUs reported by the backend (--list-devices), filled asynchronously
