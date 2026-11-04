"""llama-server process management: start, health-check, auto-retry on GPU OOM, unload."""
from __future__ import annotations

import dataclasses
import http.client
import os
import re
import shlex
import socket
import subprocess
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication

from . import paths
from .config import ModelEntry, effective_batches, vision_active
from .estimator import auto_gpu_layers
from .gguf import GGUFError, read_gguf
from .hardware import GPU, NO_WINDOW, Hardware, parse_devices, pick_device
from .i18n import tr

_NONCAUSAL = re.compile(r"non-causal attention requires n_ubatch", re.I)
_OOM = re.compile(r"out of memory|cudaMalloc failed|failed to allocate|ErrorOutOfDeviceMemory|allocateMemory", re.I)


@dataclass
class Caps:
    """What this particular llama-server build understands (parsed from --help)."""
    text: str = ""
    error: str = ""

    @property
    def fa_takes_value(self) -> bool:
        for line in self.text.splitlines():
            if "--flash-attn" in line:
                return "on|off" in line
        return False

    def has(self, flag: str) -> bool:
        return flag in self.text


def _backend_env(bd: Path) -> dict:
    env = dict(os.environ)
    env["PATH"] = str(bd) + os.pathsep + env.get("PATH", "")
    if os.name != "nt":
        env["LD_LIBRARY_PATH"] = str(bd) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    return env


def probe_caps(exe: Path) -> Caps:
    try:
        r = subprocess.run([str(exe), "--help"], capture_output=True, timeout=60,
                           cwd=str(exe.parent), creationflags=NO_WINDOW, env=_backend_env(exe.parent), stdin=subprocess.DEVNULL)
        text = (r.stdout + r.stderr).decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError) as e:
        return Caps(error=str(e))
    if "--model" not in text:
        return Caps(text=text, error=text.strip()[-600:] or "llama-server printed nothing (a DLL is probably missing)")
    return Caps(text=text)


def backend_has_gpu(bd: Path) -> bool:
    """True if the backend folder contains a GPU backend module (Vulkan / CUDA / HIP)."""
    pats = ("ggml-vulkan*", "libggml-vulkan*", "ggml-cuda*", "libggml-cuda*", "ggml-hip*", "libggml-hip*")
    return any(any(bd.glob(p)) for p in pats)


def list_devices(exe: Path) -> list[GPU]:
    try:
        r = subprocess.run([str(exe), "--list-devices"], capture_output=True, timeout=90,
                           cwd=str(exe.parent), creationflags=NO_WINDOW, env=_backend_env(exe.parent), stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_devices((r.stdout + r.stderr).decode("utf-8", "replace"))


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def build_args(entry: ModelEntry, caps: Caps, port: int, ngl: int, hw: Hardware, device_args=(), vision: bool = False,
               vram_mb: int = 0) -> list[str]:
    L = entry.load
    threads = L.n_threads or max(1, hw.cores_physical)
    tbatch = L.n_threads_batch or max(1, hw.cores_logical)
    batch, ubatch, cap = effective_batches(L, vision and caps.has("--mmproj"), vram_mb)
    if vision and caps.has("--mmproj") and not caps.has("--image-max-tokens"):
        batch = ubatch = max(batch, ubatch, 1024)      # old build: cannot cap image tokens, leave generous room
    a = [
        "-m", entry.path, "--host", "127.0.0.1", "--port", str(port),
        "-c", str(L.n_ctx), "-ngl", str(ngl), "-t", str(threads), "-tb", str(tbatch),
        "-b", str(batch), "-ub", str(ubatch), "-np", "1",
        "--cache-type-k", L.cache_type_k, "--cache-type-v", L.cache_type_v,
    ]
    a += list(device_args)
    fa = L.flash_attn
    if L.cache_type_v not in ("f16", "f32", "bf16"):
        fa = "on"                        # a quantized V cache requires flash attention
    if caps.has("--flash-attn"):
        if caps.fa_takes_value:
            a += ["-fa", fa]
        elif fa == "on":
            a += ["-fa"]
    if not L.use_mmap:
        a.append("--no-mmap")
    if L.use_mlock:
        a.append("--mlock")
    if L.jinja and caps.has("--jinja"):
        a.append("--jinja")
    if L.chat_template.strip():
        a += ["--chat-template", L.chat_template.strip()]
    if vision and entry.mmproj and caps.has("--mmproj"):
        a += ["--mmproj", entry.mmproj]
        if caps.has("--image-max-tokens"):
            a += ["--image-max-tokens", str(cap)]
        if L.mmproj_on_cpu and caps.has("--no-mmproj-offload"):
            a.append("--no-mmproj-offload")
    if L.reasoning_budget >= 0 and caps.has("--reasoning-budget"):
        a += ["--reasoning-budget", str(L.reasoning_budget)]
    if L.extra_args.strip():
        a += [t.strip('"') for t in shlex.split(L.extra_args, posix=(os.name != "nt"))]
    return a


class _HealthWatcher(QThread):
    ready = pyqtSignal()
    timed_out = pyqtSignal()

    def __init__(self, port: int, timeout_s: int = 1200) -> None:
        super().__init__()
        self.port, self.timeout_s, self._stop = port, timeout_s, False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        t0 = time.time()
        while not self._stop and time.time() - t0 < self.timeout_s:
            try:
                c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
                c.request("GET", "/health")
                r = c.getresponse()
                r.read()
                c.close()
                if r.status == 200:
                    if not self._stop:
                        self.ready.emit()
                    return
            except OSError:
                pass
            self.msleep(500)
        if not self._stop:
            self.timed_out.emit()


class ServerManager(QObject):
    state_changed = pyqtSignal(str)      # unloaded | loading | ready
    log_line = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.state = "unloaded"
        self.entry: ModelEntry | None = None
        self.port = 0
        self.proc: QProcess | None = None
        self.gpu: GPU | None = None
        self._device_args: list[str] = []
        self._vision = False
        self._vram = 0
        self.cur_ngl = 0
        self._stopping = False
        self._auto_ngl = False
        self._retries = 0
        self._buf = ""
        self._tail: deque[str] = deque(maxlen=80)
        self._watcher: _HealthWatcher | None = None
        self._caps_cache: dict[str, Caps] = {}
        self._exe: Path | None = None
        self._caps = Caps()
        self._hw = Hardware()

    @property
    def vision_loaded(self) -> bool:
        return self._vision and self.state != "unloaded"

    @property
    def pid(self) -> int:
        return int(self.proc.processId()) if self.proc is not None else 0

    def _set_state(self, s: str) -> None:
        if s != self.state:
            self.state = s
            self.state_changed.emit(s)

    # ---- public API ----------------------------------------------------
    def load(self, entry: ModelEntry, settings, hw: Hardware) -> None:
        if self.proc is not None:
            self.unload()
        exe = paths.find_backend_exe("llama-server", settings.backend_dir)
        if exe is None:
            self.failed.emit(tr("llama-server was not found. Put the backend into the 'backend' folder next to the app or set its path in Settings."))
            return
        caps = self._caps_cache.get(str(exe)) or probe_caps(exe)
        if caps.error:
            self.failed.emit(tr("The backend could not start:") + "\n" + caps.error)
            return
        self._caps_cache[str(exe)] = caps
        if not Path(entry.path).is_file():
            self.failed.emit(tr("Model file not found:") + "\n" + entry.path)
            return
        try:
            info = read_gguf(entry.path)
        except (GGUFError, OSError) as e:
            info = None
            self.log_line.emit(f"[notus] GGUF header: {e}")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            devices = list_devices(exe) if backend_has_gpu(exe.parent) else []
        finally:
            QApplication.restoreOverrideCursor()
        choice = getattr(settings, "device", "auto")
        dev = pick_device(devices, choice)
        self.gpu = dev
        self._device_args = []
        if caps.has("--device"):
            if choice == "cpu":
                self._device_args = ["--device", "none"]
            elif dev is not None and (len(devices) > 1 or choice not in ("", "auto")):
                self._device_args = ["--device", dev.dev_id]
        self._auto_ngl = entry.load.n_gpu_layers < 0
        if dev is None:
            ngl = 0
        elif self._auto_ngl:
            vis = vision_active(entry, settings)
            _b, ub_eff, _cap = effective_batches(entry.load, vis, dev.total_mb)
            reserve = 0.0
            if vis and not entry.load.mmproj_on_cpu:
                try:
                    reserve = os.path.getsize(entry.mmproj) / 1048576
                except OSError:
                    reserve = 0.0
            sized = dataclasses.replace(entry.load, n_ubatch=ub_eff)
            ngl = auto_gpu_layers(info, sized, dev.free_mb - reserve) if info else 99
        else:
            ngl = entry.load.n_gpu_layers
        self.log_line.emit("[notus] device: %s" % (("%s (%s, %d MiB free)" % (dev.dev_id, dev.name, dev.free_mb)) if dev else "CPU"))
        self.entry, self._exe, self._caps, self._hw, self._retries = entry, exe, caps, hw, 0
        self._vision = vision_active(entry, settings)
        self._vram = dev.total_mb if dev else 0
        self.port = settings.port or free_port()
        self._start(ngl)

    def unload(self) -> None:
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None
        p = self.proc
        if p is not None:
            self._stopping = True
            if p.state() != QProcess.ProcessState.NotRunning:
                if os.name == "nt":
                    p.kill()             # console apps have no window to close on Windows
                else:
                    p.terminate()
                if not p.waitForFinished(4000):
                    p.kill()
                    p.waitForFinished(2000)
            self.proc = None
            self._stopping = False
        self._set_state("unloaded")

    # ---- internals -----------------------------------------------------
    def _start(self, ngl: int) -> None:
        assert self._exe is not None and self.entry is not None
        self.cur_ngl = ngl
        self._tail.clear()
        self._buf = ""
        args = build_args(self.entry, self._caps, self.port, ngl, self._hw, self._device_args, self._vision, self._vram)
        self.log_line.emit("[notus] " + " ".join([self._exe.name] + args))
        p = QProcess(self)
        p.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        p.setWorkingDirectory(str(self._exe.parent))
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PATH", str(self._exe.parent) + os.pathsep + env.value("PATH"))
        if os.name != "nt":
            env.insert("LD_LIBRARY_PATH", str(self._exe.parent) + os.pathsep + env.value("LD_LIBRARY_PATH"))
        p.setProcessEnvironment(env)
        p.readyReadStandardOutput.connect(lambda p=p: self._on_output(p))
        p.finished.connect(lambda code, status, p=p: self._on_finished(p, code))
        p.errorOccurred.connect(lambda err, p=p: self._on_error(p, err))
        self.proc = p
        self._set_state("loading")
        p.start(str(self._exe), args)
        w = _HealthWatcher(self.port)
        w.ready.connect(self._on_ready)
        w.timed_out.connect(self._on_timeout)
        self._watcher = w
        w.start()

    def _on_output(self, p: QProcess) -> None:
        data = bytes(p.readAllStandardOutput()).decode("utf-8", "replace")
        self._buf += data
        *lines, self._buf = self._buf.split("\n")
        for ln in lines:
            ln = ln.rstrip("\r")
            if ln:
                self._tail.append(ln)
                self.log_line.emit(ln)

    def _on_ready(self) -> None:
        if self.state == "loading":
            self._set_state("ready")

    def _on_timeout(self) -> None:
        self.failed.emit(tr("The model did not become ready in time."))
        self.unload()

    def _on_error(self, p: QProcess, err) -> None:
        if p is self.proc and err == QProcess.ProcessError.FailedToStart:
            self.proc = None
            self._set_state("unloaded")
            self.failed.emit(tr("The backend could not start:") + "\n" + str(self._exe))

    def _on_finished(self, p: QProcess, code: int) -> None:
        if p is not self.proc:
            return
        self.proc = None
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None
        if self._stopping:
            return
        tail = "\n".join(list(self._tail)[-25:])
        was = self.state
        if was == "loading" and self._auto_ngl and self.cur_ngl > 0 and self._retries < 4 and _OOM.search(tail):
            self._retries += 1
            new = int(self.cur_ngl * 0.7) if self.cur_ngl > 3 else 0
            self.log_line.emit(f"[notus] GPU out of memory -> retrying with {new} GPU layers")
            self._start(new)
            return
        self._set_state("unloaded")
        parts = [tr("The backend stopped unexpectedly (exit code {code}).").format(code=code)]
        if _NONCAUSAL.search(tail):
            parts.append(tr("An image needs more tokens than the micro-batch allows. Lower “tokens per image” in Models."))
        elif _OOM.search(tail):
            parts.append(tr("Not enough memory. Lower the context size or the number of GPU layers."))
        parts.append(tail)
        self.failed.emit("\n\n".join(x for x in parts if x))
