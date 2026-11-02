"""Models page: library, per-model loading settings and the memory planner."""
from __future__ import annotations

import os
import struct
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea,
                             QSpinBox, QVBoxLayout, QWidget)

from .. import paths
from ..backend import backend_has_gpu
from ..attachments import find_mmproj
from ..config import LoadSettings, ModelEntry
from ..estimator import auto_gpu_layers, estimate, suggest_defaults
from ..gguf import GGUFError, is_first_shard_or_single, read_gguf
from ..hardware import pick_device
from ..i18n import tr
from .widgets import MemoryBar, SliderSpin

TEMPLATES = ["", "chatml", "llama3", "llama2", "mistral-v1", "mistral-v7", "gemma", "phi3", "phi4",
             "deepseek", "vicuna", "zephyr", "command-r", "openchat"]

PRESETS = {
    "balanced": dict(n_ctx=4096, n_gpu_layers=-1, n_batch=512, n_ubatch=256, flash_attn="auto",
                     cache_type_k="f16", cache_type_v="f16", use_mmap=True, use_mlock=False),
    "lowvram": dict(n_ctx=2048, n_gpu_layers=-1, n_batch=256, n_ubatch=128, flash_attn="auto",
                    cache_type_k="q8_0", cache_type_v="f16", use_mmap=True, use_mlock=False),
    "cpu": dict(n_gpu_layers=0, n_batch=512, n_ubatch=512, cache_type_k="f16", cache_type_v="f16"),
    "speed": dict(n_ctx=4096, n_gpu_layers=-1, n_batch=1024, n_ubatch=512, flash_attn="auto",
                  cache_type_k="f16", cache_type_v="f16"),
    "stream": dict(n_ctx=2048, n_gpu_layers=-1, n_batch=256, n_ubatch=128, cache_type_k="q8_0",
                   cache_type_v="f16", use_mmap=True, use_mlock=False),
}


def _card() -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("Card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(10)
    return f, lay


class ModelsPage(QWidget):
    load_requested = pyqtSignal(str)

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Page")
        self.ctx = ctx
        self.entry: ModelEntry | None = None
        self.info = None
        self._info_cache: dict = {}
        self._loading = False
        self._build()
        self.refresh_list()

    # ---- layout --------------------------------------------------------
    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        left, ll = _card()
        left.setFixedWidth(300)
        t = QLabel(tr("Library"))
        t.setObjectName("H2")
        ll.addWidget(t)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._on_row)
        ll.addWidget(self.list, 1)
        b_add = QPushButton(tr("Add model…"))
        b_add.setObjectName("Primary")
        b_add.clicked.connect(self.add_files)
        b_scan = QPushButton(tr("Scan folder…"))
        b_scan.clicked.connect(self.scan_folder)
        b_rm = QPushButton(tr("Remove from library"))
        b_rm.setObjectName("Danger")
        b_rm.clicked.connect(self.remove_current)
        for b in (b_add, b_scan, b_rm):
            ll.addWidget(b)
        hint = QLabel(tr("Files stay where they are — Notus only remembers the path. You can also drag .gguf files onto the window."))
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        ll.addWidget(hint)
        root.addWidget(left)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.editor = QWidget()
        self.editor.setObjectName("ScrollInner")
        ed = QVBoxLayout(self.editor)
        ed.setContentsMargins(0, 0, 8, 0)
        ed.setSpacing(14)
        scroll.setWidget(self.editor)
        root.addWidget(scroll, 1)

        title = QLabel(tr("Model settings"))
        title.setObjectName("Title")
        ed.addWidget(title)
        self.empty_lbl = QLabel(tr("The library is empty. Add a .gguf model to begin."))
        self.empty_lbl.setObjectName("Muted")
        ed.addWidget(self.empty_lbl)

        # --- model card
        self.card_model, ml = _card()
        h = QLabel(tr("Model"))
        h.setObjectName("H2")
        ml.addWidget(h)
        self.name_edit = QLineEdit()
        self.name_edit.editingFinished.connect(self._rename)
        ml.addWidget(self.name_edit)
        self.path_lbl = QLabel()
        self.path_lbl.setObjectName("Muted")
        self.path_lbl.setWordWrap(True)
        self.path_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        ml.addWidget(self.path_lbl)
        self.info_lbl = QLabel()
        self.info_lbl.setWordWrap(True)
        ml.addWidget(self.info_lbl)
        ed.addWidget(self.card_model)

        # --- planner card
        self.card_plan, pl = _card()
        h = QLabel(tr("Memory planner"))
        h.setObjectName("H2")
        pl.addWidget(h)
        c = self.ctx.colors
        self.bar_vram = MemoryBar(c)
        self.bar_ram = MemoryBar(c)
        pl.addWidget(self.bar_vram)
        pl.addWidget(self.bar_ram)
        self.plan_note = QLabel()
        self.plan_note.setWordWrap(True)
        self.plan_note.setTextFormat(Qt.TextFormat.RichText)
        pl.addWidget(self.plan_note)
        ed.addWidget(self.card_plan)

        # --- presets
        self.card_presets, prl = _card()
        h = QLabel(tr("Quick presets"))
        h.setObjectName("H2")
        prl.addWidget(h)
        grid = QGridLayout()
        grid.setSpacing(8)
        labels = {"balanced": tr("Balanced"), "lowvram": tr("Low VRAM (4 GB)"), "cpu": tr("CPU only"),
                  "speed": tr("Max GPU speed"), "stream": tr("Big model (SSD streaming)")}
        for i, (key, text) in enumerate(labels.items()):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, k=key: self._apply_preset(k))
            grid.addWidget(b, i // 3, i % 3)
        prl.addLayout(grid)
        ed.addWidget(self.card_presets)

        # --- load parameters
        self.card_params, pa = _card()
        h = QLabel(tr("Loading parameters"))
        h.setObjectName("H2")
        pa.addWidget(h)
        g = QGridLayout()
        g.setHorizontalSpacing(18)
        g.setVerticalSpacing(12)
        g.setColumnStretch(1, 1)
        pa.addLayout(g)
        self._row_i = 0

        self.n_ctx = QSpinBox()
        self.n_ctx.setRange(256, 1048576)
        self.n_ctx.setSingleStep(256)
        ctx_w = QWidget()
        cl = QHBoxLayout(ctx_w)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(self.n_ctx)
        for v in (2048, 4096, 8192, 16384, 32768):
            b = QPushButton("%dK" % (v // 1024))
            b.setObjectName("Chip")
            b.clicked.connect(lambda _=False, x=v: self.n_ctx.setValue(x))
            cl.addWidget(b)
        cl.addStretch(1)
        self._add(g, tr("Context size (tokens)"), ctx_w,
                  tr("How much text the model remembers. The KV cache grows with it and eats VRAM/RAM."))

        self.auto_ngl = QCheckBox(tr("Auto (fit into free VRAM)"))
        self.ngl = SliderSpin(0, 99, 1, 0)
        ngl_w = QWidget()
        nl = QVBoxLayout(ngl_w)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.addWidget(self.auto_ngl)
        nl.addWidget(self.ngl)
        self._add(g, tr("GPU layers"), ngl_w,
                  tr("How many layers live in video memory. The rest stays in RAM (and pages to SSD if RAM is short)."))

        self.threads = QSpinBox()
        self.threads.setRange(0, 256)
        self.threads.setSpecialValueText(tr("Auto"))
        self.threads_b = QSpinBox()
        self.threads_b.setRange(0, 256)
        self.threads_b.setSpecialValueText(tr("Auto"))
        th = QWidget()
        tl = QHBoxLayout(th)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(self.threads)
        tl.addWidget(QLabel(tr("prompt processing:")))
        tl.addWidget(self.threads_b)
        tl.addStretch(1)
        self._add(g, tr("CPU threads"), th, tr("Generation threads / prompt-processing threads. Auto = number of cores."))

        self.n_batch = QSpinBox()
        self.n_batch.setRange(32, 8192)
        self.n_batch.setSingleStep(32)
        self.n_ubatch = QSpinBox()
        self.n_ubatch.setRange(32, 4096)
        self.n_ubatch.setSingleStep(32)
        bw = QWidget()
        bl = QHBoxLayout(bw)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(self.n_batch)
        bl.addWidget(QLabel(tr("micro-batch:")))
        bl.addWidget(self.n_ubatch)
        bl.addStretch(1)
        self._add(g, tr("Batch size"), bw, tr("Smaller micro-batch = less VRAM for buffers, slower prompt processing."))

        self.flash = QComboBox()
        for label, v in ((tr("Auto"), "auto"), (tr("On"), "on"), (tr("Off"), "off")):
            self.flash.addItem(label, v)
        self._add(g, tr("Flash attention"), self.flash, tr("Saves memory; required for a quantized V cache."))

        self.kv_k = QComboBox()
        self.kv_v = QComboBox()
        for cb in (self.kv_k, self.kv_v):
            for t in ("f16", "q8_0", "q4_0"):
                cb.addItem(t, t)
        kvw = QWidget()
        kl = QHBoxLayout(kvw)
        kl.setContentsMargins(0, 0, 0, 0)
        kl.addWidget(QLabel("K:"))
        kl.addWidget(self.kv_k)
        kl.addWidget(QLabel("V:"))
        kl.addWidget(self.kv_v)
        kl.addStretch(1)
        self._add(g, tr("KV cache type"), kvw, tr("q8_0 halves the context memory with little quality loss."))

        self.mmap = QCheckBox(tr("Memory-map the model (mmap)"))
        self.mlock = QCheckBox(tr("Lock the model in RAM (mlock)"))
        self.jinja = QCheckBox(tr("Use the chat template from the model (--jinja)"))
        mw = QWidget()
        ml2 = QVBoxLayout(mw)
        ml2.setContentsMargins(0, 0, 0, 0)
        for cb in (self.mmap, self.mlock, self.jinja):
            ml2.addWidget(cb)
        self._add(g, tr("Memory & template"), mw,
                  tr("mmap lets the OS stream weights from SSD when RAM is short. Keep mlock off on small machines."))

        self.template = QComboBox()
        self.template.setEditable(True)
        self.template.addItems(TEMPLATES)
        self._add(g, tr("Chat template override"), self.template, tr("Leave empty to use the template stored in the GGUF file."))

        self.vision_cb = QCheckBox(tr("Enable vision for this model (loads the projector, uses extra memory)"))
        self.mmproj = QLineEdit()
        self.mmproj.setPlaceholderText(tr("none — text only"))
        b_mm = QPushButton(tr("Browse…"))
        b_mm.clicked.connect(self._browse_mmproj)
        b_mm_auto = QPushButton(tr("Find next to model"))
        b_mm_auto.clicked.connect(self._auto_mmproj)
        mmw = QWidget()
        mmv = QVBoxLayout(mmw)
        mmv.setContentsMargins(0, 0, 0, 0)
        mmv.addWidget(self.vision_cb)
        mmrow = QWidget()
        mml = QHBoxLayout(mmrow)
        mml.setContentsMargins(0, 0, 0, 0)
        mmv.addWidget(mmrow)
        mml.addWidget(self.mmproj, 1)
        mml.addWidget(b_mm)
        mml.addWidget(b_mm_auto)
        self._add(g, tr("Vision projector (mmproj)"), mmw,
                  tr("Lets the model read images. Needs the mmproj-*.gguf of this model. Reload the model after changing it."))

        self.reasoning = QSpinBox()
        self.reasoning.setRange(-1, 32768)
        self.reasoning.setSpecialValueText(tr("Unlimited"))
        self.image_tokens = QSpinBox()
        self.image_tokens.setRange(0, 4096)
        self.image_tokens.setSingleStep(64)
        self.image_tokens.setSpecialValueText(tr("Default"))
        rw = QWidget()
        rl = QHBoxLayout(rw)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel(tr("thinking tokens:")))
        rl.addWidget(self.reasoning)
        rl.addWidget(QLabel(tr("tokens per image:")))
        rl.addWidget(self.image_tokens)
        rl.addStretch(1)
        self._add(g, tr("Thinking & images"), rw,
                  tr("0 = no thinking at all. Fewer tokens per image = much faster on old hardware."))

        self.extra = QLineEdit()
        self.extra.setPlaceholderText("--rope-freq-base 10000 --no-warmup")
        self._add(g, tr("Extra llama-server arguments"), self.extra, tr("Advanced: passed to the backend as-is."))
        ed.addWidget(self.card_params)

        # --- actions
        row = QHBoxLayout()
        b_reset = QPushButton(tr("Reset to defaults"))
        b_reset.clicked.connect(lambda: self._apply_preset("balanced", reset=True))
        self.b_apply = QPushButton(tr("Save and load model"))
        self.b_apply.setObjectName("Primary")
        self.b_apply.clicked.connect(self._apply_and_load)
        row.addWidget(b_reset)
        row.addStretch(1)
        row.addWidget(self.b_apply)
        ed.addLayout(row)
        ed.addStretch(1)

        self.mmproj.editingFinished.connect(self._changed)
        self.vision_cb.toggled.connect(self._changed)
        self.reasoning.valueChanged.connect(self._changed)
        self.image_tokens.valueChanged.connect(self._changed)
        for sp in (self.n_ctx, self.threads, self.threads_b, self.n_batch, self.n_ubatch):
            sp.valueChanged.connect(self._changed)
        self.ngl.valueChanged.connect(self._changed)
        for cb in (self.auto_ngl, self.mmap, self.mlock, self.jinja):
            cb.toggled.connect(self._changed)
        for co in (self.flash, self.kv_k, self.kv_v):
            co.currentIndexChanged.connect(self._changed)
        self.template.currentTextChanged.connect(self._changed)
        self.extra.textChanged.connect(self._changed)

    def _add(self, grid: QGridLayout, label: str, widget: QWidget, hint: str = "") -> None:
        lab = QLabel(label)
        lab.setAlignment(Qt.AlignmentFlag.AlignTop)
        box = QVBoxLayout()
        box.setSpacing(2)
        box.addWidget(widget)
        if hint:
            hl = QLabel(hint)
            hl.setObjectName("Muted")
            hl.setWordWrap(True)
            box.addWidget(hl)
        grid.addWidget(lab, self._row_i, 0, Qt.AlignmentFlag.AlignTop)
        grid.addLayout(box, self._row_i, 1)
        self._row_i += 1

    # ---- library -------------------------------------------------------
    def refresh_list(self, select_id: str | None = None) -> None:
        models = self.ctx.store.s.models
        self.list.blockSignals(True)
        self.list.clear()
        for m in models:
            info = self._info_for(m)
            sub = ""
            if info:
                sub = "\n%.1f GB · %s" % (info.size_mb / 1024, info.quant or info.arch)
            it = QListWidgetItem(m.name + sub)
            it.setData(Qt.ItemDataRole.UserRole, m.id)
            self.list.addItem(it)
        self.list.blockSignals(False)
        target = select_id or (self.entry.id if self.entry else self.ctx.store.s.last_model_id)
        row = next((i for i, m in enumerate(models) if m.id == target), 0 if models else -1)
        self.list.setCurrentRow(row)
        self._on_row(row)

    def _info_for(self, entry: ModelEntry):
        try:
            mtime = os.path.getmtime(entry.path)
        except OSError:
            return None
        hit = self._info_cache.get(entry.path)
        if hit and hit[0] == mtime:
            return hit[1]
        try:
            info = read_gguf(entry.path)
        except (GGUFError, OSError, struct.error):
            info = None
        self._info_cache[entry.path] = (mtime, info)
        return info

    def _on_row(self, row: int) -> None:
        models = self.ctx.store.s.models
        has = 0 <= row < len(models)
        self.entry = models[row] if has else None
        for w in (self.card_model, self.card_plan, self.card_presets, self.card_params, self.b_apply):
            w.setVisible(has)
        self.empty_lbl.setVisible(not has)
        if has:
            self.info = self._info_for(self.entry)
            self._populate()

    def add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, tr("Add GGUF models"), self.ctx.store.s.models_dir, "GGUF (*.gguf)")
        self.add_paths(files)

    def scan_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Choose a folder with models"), self.ctx.store.s.models_dir)
        if not d:
            return
        self.ctx.store.s.models_dir = d
        found = [str(p) for p in Path(d).rglob("*.gguf")
                 if is_first_shard_or_single(p) and "mmproj" not in p.name.lower()]
        self.add_paths(found)

    def add_paths(self, files: list) -> None:
        added, errors, last = 0, [], None
        for f in files:
            if not f.lower().endswith(".gguf") or self.ctx.store.has_path(f):
                continue
            try:
                info = read_gguf(f)
            except GGUFError as e:
                errors.append("%s: %s" % (os.path.basename(f), e))
                continue
            entry = ModelEntry.create(f, suggest_defaults(info, self._vram_total()))
            entry.mmproj = find_mmproj(f)
            if self.ctx.store.add_entry(entry):
                added += 1
                last = entry.id
        if errors:
            QMessageBox.warning(self, tr("Notus"), tr("These files could not be read:") + "\n" + "\n".join(errors))
        if added:
            self.refresh_list(last)

    def remove_current(self) -> None:
        if not self.entry:
            return
        r = QMessageBox.question(self, tr("Notus"), tr("Remove “{name}” from the library? The file itself is not deleted.").format(name=self.entry.name))
        if r == QMessageBox.StandardButton.Yes:
            if self.ctx.server.entry and self.ctx.server.entry.id == self.entry.id:
                self.ctx.server.unload()
            self.ctx.store.remove_model(self.entry.id)
            self.entry = None
            self.refresh_list()

    def on_show(self) -> None:
        self.refresh_list(self.entry.id if self.entry else None)

    # ---- editor <-> entry ----------------------------------------------
    def _populate(self) -> None:
        e = self.entry
        L = e.load
        self._loading = True
        self.name_edit.setText(e.name)
        self.path_lbl.setText(e.path)
        total = (self.info.n_layers + 1) if self.info and self.info.n_layers else 99
        self.ngl.set_range(0, total)
        self.n_ctx.setValue(L.n_ctx)
        self.auto_ngl.setChecked(L.n_gpu_layers < 0)
        self.ngl.set_value(max(0, min(L.n_gpu_layers, total)))
        self.ngl.setEnabled(L.n_gpu_layers >= 0)
        self.threads.setValue(L.n_threads)
        self.threads_b.setValue(L.n_threads_batch)
        self.n_batch.setValue(L.n_batch)
        self.n_ubatch.setValue(L.n_ubatch)
        for combo, val in ((self.flash, L.flash_attn), (self.kv_k, L.cache_type_k), (self.kv_v, L.cache_type_v)):
            combo.setCurrentIndex(max(0, combo.findData(val)))
        self.mmap.setChecked(L.use_mmap)
        self.mlock.setChecked(L.use_mlock)
        self.jinja.setChecked(L.jinja)
        self.template.setCurrentText(L.chat_template)
        self.extra.setText(L.extra_args)
        self.mmproj.setText(e.mmproj)
        self.vision_cb.setChecked(e.vision)
        self.reasoning.setValue(L.reasoning_budget)
        self.image_tokens.setValue(L.image_max_tokens)
        self._loading = False
        self._refresh_info()
        self._refresh_planner()

    def _collect(self) -> None:
        L = self.entry.load
        L.n_ctx = self.n_ctx.value()
        self.ngl.setEnabled(not self.auto_ngl.isChecked())
        L.n_gpu_layers = -1 if self.auto_ngl.isChecked() else int(self.ngl.value())
        L.n_threads, L.n_threads_batch = self.threads.value(), self.threads_b.value()
        L.n_batch, L.n_ubatch = self.n_batch.value(), self.n_ubatch.value()
        L.flash_attn = self.flash.currentData() or "auto"
        L.cache_type_k = self.kv_k.currentData() or "f16"
        L.cache_type_v = self.kv_v.currentData() or "f16"
        L.use_mmap, L.use_mlock, L.jinja = self.mmap.isChecked(), self.mlock.isChecked(), self.jinja.isChecked()
        L.chat_template, L.extra_args = self.template.currentText().strip(), self.extra.text().strip()
        L.reasoning_budget, L.image_max_tokens = self.reasoning.value(), self.image_tokens.value()
        self.entry.mmproj = self.mmproj.text().strip()
        self.entry.vision = self.vision_cb.isChecked() and bool(self.entry.mmproj)

    def _changed(self, *_a) -> None:
        if self._loading or not self.entry:
            return
        self._collect()
        self._refresh_planner()
        self.ctx.store.save_later()

    def _browse_mmproj(self) -> None:
        start = str(Path(self.entry.path).parent) if self.entry else ""
        f, _ = QFileDialog.getOpenFileName(self, tr("Vision projector (mmproj)"), start, "GGUF (*.gguf)")
        if f:
            self.mmproj.setText(f)
            self._changed()

    def _auto_mmproj(self) -> None:
        if self.entry:
            found = find_mmproj(self.entry.path)
            self.mmproj.setText(found)
            self._changed()
            if not found:
                QMessageBox.information(self, tr("Notus"), tr("No mmproj-*.gguf file was found in the model's folder."))

    def _rename(self) -> None:
        if self.entry and self.name_edit.text().strip() and self.name_edit.text().strip() != self.entry.name:
            self.entry.name = self.name_edit.text().strip()
            self.ctx.store.save_later()
            self.ctx.store.models_changed.emit()
            row = self.list.currentRow()
            self.refresh_list(self.entry.id)
            self.list.setCurrentRow(row)

    def _apply_preset(self, key: str, reset: bool = False) -> None:
        if not self.entry:
            return
        base = suggest_defaults(self.info, self._vram_total()) if reset else self.entry.load
        for k, v in PRESETS[key].items():
            setattr(base, k, v)
        if reset:
            base.n_ctx = suggest_defaults(self.info, self._vram_total()).n_ctx
            self.entry.load = base
        self._populate()
        self.ctx.store.save_later()

    def _apply_and_load(self) -> None:
        if self.entry:
            self._collect()
            self.ctx.store.s.last_model_id = self.entry.id
            self.ctx.store.save()
            self.load_requested.emit(self.entry.id)

    # ---- info + planner ------------------------------------------------
    def _refresh_info(self) -> None:
        i = self.info
        if not i:
            self.info_lbl.setText("<span style='color:%s'>%s</span>" % (self.ctx.colors["danger"], tr("The file is missing or is not a valid GGUF.")))
            return
        parts = [
            "<b>%s</b>: %s" % (tr("Architecture"), i.arch),
            "<b>%s</b>: %.2f GB" % (tr("Size"), i.size_mb / 1024),
            "<b>%s</b>: %s" % (tr("Quantization"), i.quant or "?"),
            "<b>%s</b>: %d" % (tr("Layers"), i.n_layers),
            "<b>%s</b>: %d" % (tr("Trained context"), i.n_ctx_train),
        ]
        if i.n_experts:
            parts.append("<b>MoE</b>: %d %s" % (i.n_experts, tr("experts")))
        parts.append("<b>%s</b>: %s" % (tr("Chat template"), tr("yes") if i.has_chat_template else tr("no")))
        self.info_lbl.setText(" &nbsp;·&nbsp; ".join(parts))

    def _device(self):
        return pick_device(self.ctx.devices, self.ctx.store.s.device)

    def _vram_total(self) -> int:
        d = self._device()
        return d.total_mb if d else 0

    def _gpu_ok(self) -> bool:
        exe = paths.find_backend_exe("llama-server", self.ctx.store.s.backend_dir)
        return self._device() is not None and exe is not None and backend_has_gpu(exe.parent)

    def _refresh_planner(self) -> None:
        if not self.entry or not self.info:
            self.bar_vram.set_data("", [], 0)
            self.bar_ram.set_data("", [], 0)
            self.plan_note.setText("")
            return
        c, hw, L, info = self.ctx.colors, self.ctx.hw, self.entry.load, self.info
        gpu_ok = self._gpu_ok()
        if L.n_gpu_layers < 0:
            ngl = auto_gpu_layers(info, L, self._device().free_mb) if gpu_ok else 0
            self._loading = True
            self.ngl.set_value(ngl)
            self._loading = False
        else:
            ngl = L.n_gpu_layers
        est = estimate(info, L, ngl, gpu_ok)
        cyan = "#1fb6d4"
        if gpu_ok:
            self.bar_vram.set_data("VRAM — " + self._device().name, [
                (tr("Weights"), est.weights_gpu_mb, c["accent"]), (tr("KV cache"), est.kv_gpu_mb, cyan),
                (tr("Buffers"), est.overhead_gpu_mb, c["warn"])], self._vram_total())
        else:
            self.bar_vram.set_data("VRAM — " + tr("not used"), [], 0)
        self.bar_ram.set_data("RAM", [
            (tr("Weights"), est.weights_cpu_mb, c["accent"]), (tr("KV cache"), est.kv_cpu_mb, cyan),
            (tr("Runtime"), est.runtime_cpu_mb, c["warn"])], hw.ram_total_mb)
        notes = ["%s: <b>%d / %d</b>" % (tr("GPU layers"), est.gpu_layers, est.total_layers)]
        bad = "<span style='color:%s'>" % c["danger"]
        warn = "<span style='color:%s'>" % c["warn"]
        if not gpu_ok:
            notes.append(tr("No usable GPU was found (or CPU-only mode is selected) — the model runs on the CPU."))
        if gpu_ok and est.vram_mb > self._vram_total():
            notes.append(bad + tr("Does not fit into VRAM. Lower the GPU layers, the context or the micro-batch.") + "</span>")
        if hw.ram_total_mb and est.ram_mb > hw.ram_total_mb * 0.9:
            notes.append(warn + tr("More than the RAM: pages will be streamed from SSD through mmap. It works, but slowly. Keep mmap on and mlock off.") + "</span>")
        if L.use_mlock and est.ram_mb > hw.ram_free_mb:
            notes.append(bad + tr("mlock needs more free RAM than is available right now.") + "</span>")
        if info.n_ctx_train and L.n_ctx > info.n_ctx_train:
            notes.append(warn + tr("The context is larger than the model was trained for ({n}); quality may drop.").format(n=info.n_ctx_train) + "</span>")
        if L.cache_type_v not in ("f16", "f32", "bf16") and L.flash_attn == "off":
            notes.append(warn + tr("A quantized V cache needs flash attention; Notus will turn it on automatically.") + "</span>")
        self.plan_note.setText("<br>".join(notes))
