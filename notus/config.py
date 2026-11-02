"""Plain dataclasses describing settings. No Qt imports here."""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field, fields
from pathlib import Path


def from_dict(cls, data):
    """Build a dataclass from a dict, ignoring unknown keys (forward/backward compatible)."""
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in (data or {}).items() if k in names})


@dataclass
class LoadSettings:
    """Everything passed to llama-server when a model is loaded."""
    n_ctx: int = 4096
    n_gpu_layers: int = -1          # -1 = automatic (fit into free VRAM)
    n_threads: int = 0              # 0 = automatic
    n_threads_batch: int = 0        # 0 = automatic
    n_batch: int = 512
    n_ubatch: int = 256
    flash_attn: str = "auto"        # auto | on | off
    cache_type_k: str = "f16"
    cache_type_v: str = "f16"
    use_mmap: bool = True
    use_mlock: bool = False
    jinja: bool = True
    chat_template: str = ""         # empty = use the template stored in the GGUF
    reasoning_budget: int = -1      # -1 = unlimited, 0 = no thinking at all, N = max thinking tokens
    image_max_tokens: int = 0       # 0 = model default; lower = faster image processing on old hardware
    extra_args: str = ""


@dataclass
class GenSettings:
    """Sampling / generation parameters sent with every chat request."""
    system_prompt: str = ""
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    min_p: float = 0.05
    repeat_penalty: float = 1.1
    max_tokens: int = 1024
    seed: int = -1
    think: str = "auto"             # auto | on | off  (models with a thinking mode, e.g. Qwen3)


@dataclass
class ModelEntry:
    id: str
    name: str
    path: str
    mmproj: str = ""               # vision projector (mmproj-*.gguf)
    vision: bool = False            # load the projector (extra memory!) so the model can read images
    load: LoadSettings = field(default_factory=LoadSettings)
    gen: GenSettings = field(default_factory=GenSettings)

    @staticmethod
    def create(path: str, load: LoadSettings | None = None) -> "ModelEntry":
        p = Path(path)
        return ModelEntry(id=uuid.uuid4().hex[:12], name=p.stem, path=str(p), load=load or LoadSettings())

    @staticmethod
    def from_dict(d) -> "ModelEntry":
        d = d or {}
        path = d.get("path", "")
        return ModelEntry(
            id=d.get("id") or uuid.uuid4().hex[:12],
            name=d.get("name") or Path(path).stem,
            path=path,
            mmproj=d.get("mmproj") or "",
            vision=bool(d.get("vision", False)),
            load=from_dict(LoadSettings, d.get("load")),
            gen=from_dict(GenSettings, d.get("gen")),
        )


@dataclass
class Assistant:
    """A reusable persona: system prompt + optional overrides for sampling and thinking."""
    id: str
    name: str
    system_prompt: str = ""
    temperature: float = -1.0       # -1 = keep the model's own temperature
    think: str = "inherit"          # inherit | auto | on | off
    builtin_key: str = ""           # non-empty for the shipped assistants

    @staticmethod
    def from_dict(d) -> "Assistant":
        d = dict(d or {})
        d.setdefault("id", uuid.uuid4().hex[:12])
        return from_dict(Assistant, d)


@dataclass
class AppSettings:
    language: str = "auto"          # auto | en | ru
    theme: str = "dark"             # dark | light
    accent: str = "violet"
    font_size: int = 10
    backend_dir: str = ""
    models_dir: str = ""
    port: int = 0                   # 0 = pick a free port automatically
    device: str = "auto"            # auto | cpu | backend device id (e.g. Vulkan0)
    auto_unload_minutes: int = 0    # 0 = never
    last_model_id: str = ""
    show_params_panel: bool = True
    show_thinking: bool = True      # show the model's reasoning text (collapsed) in bubbles
    # --- optional modules (a disabled module is not loaded and costs nothing) ---
    mod_vision: bool = True
    mod_files: bool = True
    mod_assistants: bool = True
    mod_thinking: bool = True
    mod_share: bool = True
    mod_monitor: bool = True
    last_assistant_id: str = ""
    assistants_seeded: bool = False
    # --- sharing (local API + web chat) ---
    share_enabled: bool = False
    share_lan: bool = False         # False = 127.0.0.1 only, True = 0.0.0.0 (local network)
    share_port: int = 8080
    share_key: str = ""
    share_allow_switch: bool = True
    share_autoload: bool = True
    share_webui: bool = True
    models: list = field(default_factory=list)   # list[ModelEntry]
    assistants: list = field(default_factory=list)   # list[Assistant]


def vision_active(entry, settings) -> bool:
    """True if images can be used with this model right now (module on, projector enabled and present)."""
    return bool(settings.mod_vision and entry is not None and entry.vision and entry.mmproj and os.path.isfile(entry.mmproj))
