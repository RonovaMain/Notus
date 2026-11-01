"""Plain dataclasses describing settings. No Qt imports here."""
from __future__ import annotations

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


@dataclass
class ModelEntry:
    id: str
    name: str
    path: str
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
            load=from_dict(LoadSettings, d.get("load")),
            gen=from_dict(GenSettings, d.get("gen")),
        )


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
    models: list = field(default_factory=list)   # list[ModelEntry]
