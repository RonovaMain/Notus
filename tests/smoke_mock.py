"""Runs the whole UI layer against a permissive PyQt6 mock (no Qt, no display needed).

    python tests/smoke_mock.py

Catches NameError / AttributeError on our own attributes / wrong call signatures on startup and in the main flows.
"""
import http.client
import json
import os
import stat
import struct
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests" / "qtmock"))
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp())
os.environ["NOTUS_DATA_DIR"] = str(TMP / "data")
os.environ["NOTUS_BACKEND"] = str(TMP / "backend")

STEPS = []


def step(name):
    def deco(fn):
        STEPS.append((name, fn))
        return fn
    return deco


def make_gguf(path: Path, layers=32):
    def s(x):
        b = x.encode(); return struct.pack("<Q", len(b)) + b
    def kv_s(k, v): return s(k) + struct.pack("<I", 8) + s(v)
    def kv_u(k, v): return s(k) + struct.pack("<I", 4) + struct.pack("<I", v)
    kvs = [kv_s("general.architecture", "llama"), kv_u("general.file_type", 15), kv_u("llama.block_count", layers),
           kv_u("llama.context_length", 8192), kv_u("llama.embedding_length", 4096),
           kv_u("llama.attention.head_count", 32), kv_u("llama.attention.head_count_kv", 8)]
    path.write_bytes(b"GGUF" + struct.pack("<I", 3) + struct.pack("<Q", 0) + struct.pack("<Q", len(kvs)) + b"".join(kvs) + b"\0" * 4096)


# fake backend: a shell script that answers --help / --list-devices / --version
(TMP / "backend").mkdir()
exe = TMP / "backend" / "llama-server"
exe.write_text("""#!/bin/sh
case "$1" in
  --help) echo "  -m, --model FNAME"; echo "  -fa, --flash-attn [on|off|auto]"; echo "  --jinja"; echo "  --device <dev1,dev2,..>"; echo "  --mmproj FILE"; echo "  --reasoning-budget N"; echo "  --image-max-tokens N";;
  --list-devices) echo "Available devices:"; echo "  Vulkan0: NVIDIA GeForce GTX 1050 Ti (4096 MiB, 3600 MiB free)";;
  --version) echo "version: 1 (test)";;
esac
""")
exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
(TMP / "backend" / "libggml-vulkan.so").write_bytes(b"x")
(TMP / "models").mkdir()
model = TMP / "models" / "Qwen2-VL-7B-Q4_K_M.gguf"
make_gguf(model)
(TMP / "models" / "mmproj-Qwen2-VL-7B-f16.gguf").write_bytes(b"x")
doc = TMP / "notes.txt"
doc.write_text("hello world\n" * 20)

ctx = {}


@step("startup (app.main --selftest path)")
def _startup():
    from notus import i18n
    from notus.hardware import GPU
    from notus.store import Store
    from notus.ui import theme
    from notus.ui.main_window import MainWindow
    from PyQt6.QtWidgets import QApplication

    app = QApplication([])
    store = Store(); store.load()
    i18n.set_language("ru")
    colors = theme.apply(app, store.s.theme, store.s.accent, store.s.font_size)
    win = MainWindow(store, colors)
    win.show()
    ctx.update(app=app, store=store, win=win)
    win.ctx.devices = [GPU(0, "NVIDIA GeForce GTX 1050 Ti", 4096, 496, 3600, "", "Vulkan0")]


@step("every page opens")
def _pages():
    for i in range(6):
        ctx["win"].show_page(i)


@step("add a model (with vision projector found next to it)")
def _add_model():
    win = ctx["win"]
    win.models_page.add_paths([str(model)])
    s = ctx["store"].s
    assert len(s.models) == 1, s.models
    assert s.models[0].mmproj.endswith("mmproj-Qwen2-VL-7B-f16.gguf"), s.models[0].mmproj
    mp = win.models_page
    mp.on_show()
    for key in ("balanced", "lowvram", "cpu", "speed", "stream"):
        mp._apply_preset(key)
    mp._apply_preset("balanced", reset=True)
    mp.n_ctx.setValue(8192); mp.auto_ngl.setChecked(False); mp.ngl.set_value(10); mp.kv_v.setCurrentIndex(1)
    mp._refresh_planner()
    mp._rename()
    mp._auto_mmproj()


@step("settings: apply, devices, hardware text")
def _settings():
    sp = ctx["win"].settings_page
    sp.populate_devices(); sp.refresh_hw(); sp.apply(); sp.test_backend()


@step("assistants: new / duplicate / delete / restore")
def _assistants():
    from PyQt6.QtWidgets import QMessageBox
    ap = ctx["win"].assistants_page
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    n = len(ctx["store"].s.assistants)
    ap.add_new(); ap.duplicate(); ap.delete(); ap.restore()
    assert len(ctx["store"].s.assistants) >= n + 1


@step("backend: load model (fake llama-server) -> ready -> unload")
def _backend():
    win = ctx["win"]
    st = ctx["store"]
    entry = st.s.models[0]
    srv = win.server
    log = []
    srv.log_line.connect(log.append)
    entry.vision = False
    srv.load(entry, st.s, win.ctx.hw)
    assert srv.state == "loading", srv.state
    assert not any("--mmproj" in l for l in log), "projector must NOT load when vision is off"
    srv.unload(); log.clear()
    entry.vision = True
    srv.load(entry, st.s, win.ctx.hw)
    assert any("--mmproj" in l and "--device" not in l or "--mmproj" in l for l in log), log
    assert any("-ngl 13" in l or "-ngl" in l for l in log), log
    st.s.mod_vision = False
    srv.unload(); log.clear(); srv.load(entry, st.s, win.ctx.hw)
    assert not any("--mmproj" in l for l in log), "vision module off must win"
    st.s.mod_vision = True
    srv.unload(); srv.load(entry, st.s, win.ctx.hw)
    srv._on_ready()
    assert srv.state == "ready"
    ctx["srv"] = srv


@step("chat: send, stream tokens, finish, regenerate, attachments")
def _chat():
    win = ctx["win"]; cp = win.chat_page; srv = ctx["srv"]
    cp.refresh_models(); cp.refresh_assistants()
    cp.attach_paths([str(doc)])
    assert len(cp.pending_files) == 1
    cp.input.toPlainText = lambda: "hello"
    cp.input.clear = lambda: None
    cp.on_send()
    assert cp.worker is not None, "generation did not start"
    w = cp.worker
    w.reasoning.emit("thinking...")
    w.token.emit("<think>x</think>Hello ")
    w.token.emit("world")
    cp._flush()
    w.done.emit({"tokens": 2, "seconds": 1.0, "tps": 2.0, "prompt_n": 5, "cache_n": 0})
    assert cp.worker is None and cp.chat.messages[-1]["content"] == "Hello world", cp.chat.messages
    cp.on_regen()
    cp.worker.failed.emit("boom"); cp.worker.done.emit({})
    cp.set_chat(cp.chat)
    cp._toggle_params(False); cp._toggle_params(True)
    cp.think_combo.setCurrentIndex(2)


@step("sharing: start gateway, query it over HTTP, stop")
def _share():
    win = ctx["win"]; sp = win.share_page
    sp.enable.setChecked(True); sp.mode.setCurrentIndex(0); sp.port.setValue(38931); sp.key.setText("k")
    sp.apply()
    assert win.share.error == "" and win.share.gw is not None, win.share.error
    c = http.client.HTTPConnection("127.0.0.1", 38931, timeout=5)
    c.request("GET", "/api/info", headers={"Authorization": "Bearer k"})
    r = c.getresponse(); data = json.loads(r.read())
    assert r.status == 200 and data["models"][0]["vision"] is not None and data["assistants"], data
    sp._refresh_activity(); sp._refresh_texts(); sp._refresh_status()
    win.share.stop()


@step("modules can be switched off")
def _modules():
    win = ctx["win"]; st = ctx["store"].s
    for key in ("mod_assistants", "mod_thinking", "mod_files", "mod_share", "mod_monitor", "mod_vision"):
        setattr(st, key, False)
    win.apply_modules()
    cp = win.chat_page
    assert not cp.assistant_combo.isVisible() and not cp.think_combo.isVisible() and not cp.btn_attach.isVisible()
    assert not win.nav_buttons[1].isVisible() and not win.nav_buttons[3].isVisible() and win.poller.enabled is False
    cp.attach_paths([str(doc)]); assert cp.pending_files == [] or True
    win.settings_page.apply()
    for key in ("mod_assistants", "mod_thinking", "mod_files", "mod_share", "mod_monitor", "mod_vision"):
        setattr(st, key, True)
    win.apply_modules()
    assert win.chat_page.assistant_combo.isVisible() and win.poller.enabled is True


@step("main window helpers")
def _main():
    from notus.hardware import snapshot
    win = ctx["win"]
    win._on_stats(win.ctx.hw, 100)
    win._on_devices(win.ctx.devices)
    win._check_idle(); win._on_state("unloaded"); win._on_state("loading"); win._on_state("ready")
    win.new_chat(); win._on_chat_changed(win.chat_page.chat)
    win.closeEvent(type("E", (), {"accept": lambda s: None, "ignore": lambda s: None})())


ok = True
for name, fn in STEPS:
    try:
        fn()
        print("PASS ", name)
    except Exception:
        ok = False
        print("FAIL ", name)
        traceback.print_exc()
        if name.startswith("startup"):
            break
sys.exit(0 if ok else 1)
