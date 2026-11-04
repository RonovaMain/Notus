"""Streaming chat client for llama-server's OpenAI-compatible endpoint (localhost only)."""
from __future__ import annotations

import http.client
import json
import time

from PyQt6.QtCore import QThread, pyqtSignal

from .config import GenSettings


def approx_tokens(text: str) -> int:
    return len(text) // 3 + 1            # deliberately pessimistic


IMAGE_TOKENS = 900                       # rough cost of one image for the budget


def message_text(m: dict) -> str:
    """User text with attached documents in front of it."""
    parts = []
    for f in m.get("files") or []:
        note = "\n[…file truncated…]" if f.get("truncated") else ""
        parts.append("[Attached file: %s]\n```\n%s\n```%s" % (f.get("name", "file"), f.get("text", ""), note))
    if m.get("content"):
        parts.append(m["content"])
    elif m.get("files"):
        parts.append("Summarize the attached file(s) briefly.")
    return "\n\n".join(x for x in parts if x)


def _cost(m: dict, image_tokens: int = IMAGE_TOKENS) -> int:
    return approx_tokens(message_text(m)) + image_tokens * len(m.get("images") or []) + 8


def fit_messages(system: str, history: list, n_ctx: int, max_tokens: int, vision: bool = False,
                 image_tokens: int = IMAGE_TOKENS) -> list[dict]:
    """API messages that fit the context window (oldest turns dropped first).

    Only images of the newest user message are sent; older images become a short note (saves a lot of
    prompt processing time on slow hardware).
    """
    reserve = max_tokens if max_tokens > 0 else n_ctx // 4
    budget = max(256, n_ctx - reserve - 64)
    if system.strip():
        budget -= approx_tokens(system)
    last_user = max((i for i, m in enumerate(history) if m["role"] == "user"), default=-1)
    kept: list[tuple[int, dict]] = []
    for i in range(len(history) - 1, -1, -1):
        m = history[i]
        cost = _cost(m, image_tokens) if (i == last_user and vision) else approx_tokens(message_text(m)) + 8
        if kept and cost > budget:
            break
        kept.append((i, m))
        budget -= cost
    kept.reverse()
    out: list[dict] = []
    if system.strip():
        out.append({"role": "system", "content": system})
    for i, m in kept:
        text = message_text(m)
        imgs = m.get("images") or []
        if m["role"] == "user" and imgs:
            if vision and i == last_user:
                content = [{"type": "text", "text": text or "Describe the image."}]
                content += [{"type": "image_url", "image_url": {"url": u}} for u in imgs]
                out.append({"role": "user", "content": content})
                continue
            text = (text + "\n" if text else "") + "[%d image(s) were attached here]" % len(imgs)
        out.append({"role": m["role"], "content": text})
    return out


def split_think(text: str) -> tuple[str, str]:
    """Separate <think>…</think> blocks that some models put into the normal answer text."""
    if "<think>" not in text:
        return "", text
    start = text.index("<think>")
    end = text.find("</think>", start)
    if end == -1:
        return text[start + 7:], text[:start]
    return text[start + 7:end].strip(), (text[:start] + text[end + 8:]).lstrip()


class ChatWorker(QThread):
    token = pyqtSignal(str)
    reasoning = pyqtSignal(str)
    failed = pyqtSignal(str)
    done = pyqtSignal(dict)

    def __init__(self, port: int, messages: list, gen: GenSettings, think: str = "auto", parent=None) -> None:
        super().__init__(parent)
        self.port, self.messages, self.gen, self.think = port, messages, gen, think
        self._stop = False
        self._conn: http.client.HTTPConnection | None = None

    def stop(self) -> None:
        self._stop = True
        try:
            if self._conn is not None:
                self._conn.close()
        except Exception:
            pass

    def run(self) -> None:
        g = self.gen
        payload = {
            "model": "notus", "messages": self.messages, "stream": True, "cache_prompt": True,
            "temperature": g.temperature, "top_p": g.top_p, "top_k": g.top_k,
            "min_p": g.min_p, "repeat_penalty": g.repeat_penalty,
        }
        if g.max_tokens > 0:
            payload["max_tokens"] = g.max_tokens
        if g.seed >= 0:
            payload["seed"] = g.seed
        if self.think in ("on", "off"):
            payload["chat_template_kwargs"] = {"enable_thinking": self.think == "on"}
        n, t0, t_first, timings = 0, time.time(), None, {}
        try:
            self._conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3600)
            self._conn.request("POST", "/v1/chat/completions", json.dumps(payload), {"Content-Type": "application/json"})
            resp = self._conn.getresponse()
            if resp.status != 200:
                body = resp.read().decode("utf-8", "replace")
                try:
                    err = json.loads(body).get("error", body)
                    body = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                except ValueError:
                    pass
                raise RuntimeError(body.strip() or f"HTTP {resp.status}")
            while not self._stop:
                raw = resp.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except ValueError:
                    continue
                if "error" in obj:
                    err = obj["error"]
                    raise RuntimeError(err.get("message", str(err)) if isinstance(err, dict) else str(err))
                if isinstance(obj.get("timings"), dict):
                    timings = obj["timings"]
                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                rc = delta.get("reasoning_content")
                if rc:
                    self.reasoning.emit(rc)
                c = delta.get("content")
                if c:
                    if t_first is None:
                        t_first = time.time()
                    n += 1
                    self.token.emit(c)
        except Exception as e:                      # connection closed by stop() is expected
            if not self._stop:
                self.failed.emit(str(e))
        finally:
            try:
                if self._conn is not None:
                    self._conn.close()
            except Exception:
                pass
        dt = time.time() - t0
        gen_dt = (time.time() - t_first) if t_first else 0.0
        tps = float(timings.get("predicted_per_second") or 0) or ((n - 1) / gen_dt if gen_dt > 0 and n > 1 else 0.0)
        self.done.emit({"tokens": int(timings.get("predicted_n") or n), "seconds": dt, "tps": tps,
                        "prompt_n": int(timings.get("prompt_n") or 0), "cache_n": int(timings.get("cache_n") or 0),
                        "stopped": self._stop})
