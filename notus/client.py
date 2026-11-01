"""Streaming chat client for llama-server's OpenAI-compatible endpoint (localhost only)."""
from __future__ import annotations

import http.client
import json
import time

from PyQt6.QtCore import QThread, pyqtSignal

from .config import GenSettings


def approx_tokens(text: str) -> int:
    return len(text) // 3 + 1            # deliberately pessimistic


def fit_messages(system: str, history: list, n_ctx: int, max_tokens: int) -> list[dict]:
    """Drop the oldest turns so that the prompt (+ reply budget) fits into the context window."""
    reserve = max_tokens if max_tokens > 0 else n_ctx // 4
    budget = max(256, n_ctx - reserve - 64)
    if system.strip():
        budget -= approx_tokens(system)
    kept: list[dict] = []
    for m in reversed(history):
        cost = approx_tokens(m["content"]) + 8
        if kept and cost > budget:
            break
        kept.append({"role": m["role"], "content": m["content"]})
        budget -= cost
    kept.reverse()
    if system.strip():
        kept.insert(0, {"role": "system", "content": system})
    return kept


class ChatWorker(QThread):
    token = pyqtSignal(str)
    reasoning = pyqtSignal(str)
    failed = pyqtSignal(str)
    done = pyqtSignal(dict)

    def __init__(self, port: int, messages: list, gen: GenSettings, parent=None) -> None:
        super().__init__(parent)
        self.port, self.messages, self.gen = port, messages, gen
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
                        "prompt_n": int(timings.get("prompt_n") or 0), "stopped": self._stop})
