"""Sharing gateway: OpenAI-compatible API + built-in web chat (standard library only, no Qt).

One stable address (host:port) in front of the internal llama-server:
  * /v1/chat/completions, /v1/completions, /v1/models   - for VS Code, Continue, scripts ...
  * /                                                     - mobile-friendly web chat (phone / laptop browser)
  * /api/info, /api/load, /api/unload                     - used by the web chat
The gateway can load / switch models on demand through the controller (the Qt side).
"""
from __future__ import annotations

import hmac
import http.client
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 64 * 1024 * 1024
PROXY_PATHS = {
    "/v1/chat/completions": "/v1/chat/completions",
    "/chat/completions": "/v1/chat/completions",
    "/v1/completions": "/v1/completions",
    "/completions": "/v1/completions",
}
LOAD_TIMEOUT = 900.0


class Controller:
    """What the gateway needs from the application (implemented on the Qt side)."""

    def info(self) -> dict:                     # models, assistants, state ...
        raise NotImplementedError

    def ensure_model(self, requested, allow_switch: bool, autoload: bool, timeout: float):
        """Make sure a model is ready. Returns (internal_port or None, error_message)."""
        raise NotImplementedError

    def unload_model(self) -> None:
        raise NotImplementedError

    def touch(self) -> None:                    # remote activity (for the idle auto-unload)
        pass


class Gateway:
    def __init__(self, controller: Controller, host: str, port: int, api_key: str = "", allow_switch: bool = True,
                 autoload: bool = True, webui: bool = True, version: str = "") -> None:
        self.controller = controller
        self.host, self.port, self.api_key = host, port, api_key
        self.allow_switch, self.autoload, self.webui, self.version = allow_switch, autoload, webui, version
        self.stats = {"requests": 0, "errors": 0, "last_client": "", "last_time": 0.0}
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ---- lifecycle -----------------------------------------------------
    def start(self) -> None:
        """Raises OSError if the port is busy."""
        class Server(ThreadingHTTPServer):
            daemon_threads = True
            allow_reuse_address = os.name != "nt"     # on Windows SO_REUSEADDR would hide port conflicts

        self._server = Server((self.host, self.port), _make_handler(self))
        self._thread = threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.3},
                                        name="notus-gateway", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    @property
    def running(self) -> bool:
        return self._server is not None

    def _note(self, client: str, error: bool = False) -> None:
        self.stats["requests"] += 1
        self.stats["errors"] += 1 if error else 0
        self.stats["last_client"], self.stats["last_time"] = client, time.time()


def _make_handler(gw: Gateway):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Notus"
        protocol_version = "HTTP/1.0"            # responses end by closing the connection (works for SSE streams)

        def log_message(self, *args) -> None:
            pass

        # ---- helpers ---------------------------------------------------
        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "authorization, content-type, x-api-key")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

        def _send(self, status: int, body: bytes, ctype: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self._cors()
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, obj) -> None:
            self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _error(self, status: int, message: str) -> None:
            gw._note(self.client_address[0], True)
            self._json(status, {"error": {"message": message, "type": "notus_error", "code": status}})

        def _authorized(self) -> bool:
            if not gw.api_key:
                return True
            auth = self.headers.get("Authorization", "")
            token = auth[7:].strip() if auth.lower().startswith("bearer ") else self.headers.get("x-api-key", "")
            return hmac.compare_digest(token.encode("utf-8"), gw.api_key.encode("utf-8"))

        def _body(self) -> bytes | None:
            try:
                n = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self._error(411, "Content-Length required")
                return None
            if n > MAX_BODY:
                self._error(413, "request too large")
                return None
            return self.rfile.read(n)

        # ---- routes ----------------------------------------------------
        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self._cors()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                if not gw.webui:
                    return self._error(404, "the web chat is disabled in Notus settings")
                from .webui import HTML
                return self._send(200, HTML.replace("__VERSION__", gw.version).encode("utf-8"), "text/html; charset=utf-8")
            if path == "/health":
                info = gw.controller.info()
                return self._json(200, {"status": "ok", "state": info.get("state"), "model": info.get("loaded")})
            if path == "/favicon.ico":
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if not self._authorized():
                return self._error(401, "invalid or missing API key")
            if path in ("/v1/models", "/models"):
                info = gw.controller.info()
                data = [{"id": m["name"], "object": "model", "created": 0, "owned_by": "notus"} for m in info["models"]]
                return self._json(200, {"object": "list", "data": data})
            if path == "/api/info":
                info = gw.controller.info()
                info.update(version=gw.version, allow_switch=gw.allow_switch)
                return self._json(200, info)
            self._error(404, "unknown endpoint")

        def do_POST(self) -> None:
            path = self.path.split("?", 1)[0]
            if not self._authorized():
                return self._error(401, "invalid or missing API key")
            body = self._body()
            if body is None:
                return
            if path == "/api/load":
                if not gw.allow_switch:
                    return self._error(403, "model switching is disabled in Notus settings")
                try:
                    requested = json.loads(body or b"{}").get("model")
                except (ValueError, AttributeError):
                    requested = None
                port, err = gw.controller.ensure_model(requested, True, True, LOAD_TIMEOUT)
                if port is None:
                    return self._error(503, err)
                gw.controller.touch()
                return self._json(200, {"ok": True, "info": gw.controller.info()})
            if path == "/api/unload":
                if not gw.allow_switch:
                    return self._error(403, "model switching is disabled in Notus settings")
                gw.controller.unload_model()
                return self._json(200, {"ok": True})
            target = PROXY_PATHS.get(path)
            if target is None:
                return self._error(404, "unknown endpoint")
            self._proxy(target, body)

        def _proxy(self, target: str, body: bytes) -> None:
            try:
                data = json.loads(body or b"{}")
                requested = data.get("model") if isinstance(data, dict) else None
            except ValueError:
                return self._error(400, "invalid JSON")
            port, err = gw.controller.ensure_model(requested, gw.allow_switch, gw.autoload, LOAD_TIMEOUT)
            if port is None:
                return self._error(503, err)
            gw.controller.touch()
            gw._note(self.client_address[0])
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3600)
            started = False
            try:
                conn.request("POST", target, body, {"Content-Type": "application/json"})
                resp = conn.getresponse()
                self.send_response(resp.status)
                self.send_header("Content-Type", resp.getheader("Content-Type") or "application/json")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Accel-Buffering", "no")
                self._cors()
                self.end_headers()
                started = True
                while True:
                    chunk = resp.read1(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass                              # the client left; closing the backend connection stops generation
            except (OSError, http.client.HTTPException) as e:      # includes IncompleteRead (backend crashed)
                if not started:
                    self._error(502, "the model backend is not reachable: %s" % e)
                else:                         # the stream was already open: finish it with an error event
                    gw._note(self.client_address[0], True)
                    try:
                        msg = {"error": {"message": "The model on the computer stopped while answering (%s)." % e}}
                        self.wfile.write(("data: %s\n\n" % json.dumps(msg)).encode("utf-8"))
                        self.wfile.flush()
                    except OSError:
                        pass
            finally:
                conn.close()

    return Handler
