"""Rough memory planner: how much VRAM / RAM a model + KV cache will take."""
from __future__ import annotations

from dataclasses import dataclass

from .config import LoadSettings
from .gguf import GGUFInfo

# bytes per element of the KV cache for each cache type
_BPE = {
    "f32": 4.0, "f16": 2.0, "bf16": 2.0, "q8_0": 34 / 32, "q5_1": 24 / 32,
    "q5_0": 22 / 32, "q4_1": 20 / 32, "q4_0": 18 / 32, "iq4_nl": 18 / 32,
}
GPU_CONTEXT_MB = 260       # driver context + backend workspace (Vulkan / CUDA)
RUNTIME_MB = 350           # llama-server's own CPU-side buffers


def compute_buffer_mb(n_ubatch: int) -> float:
    return 140 + 0.6 * n_ubatch


def kv_cache_mb(info: GGUFInfo, n_ctx: int, type_k: str, type_v: str) -> float:
    layers = info.n_layers or 32
    n_head = info.n_head or 32
    n_kv = info.n_head_kv or n_head
    n_embd = info.n_embd or 4096
    kl = info.key_length or n_embd // max(n_head, 1)
    vl = info.value_length or kl
    k = layers * n_ctx * n_kv * kl * _BPE.get(type_k, 2.0)
    v = layers * n_ctx * n_kv * vl * _BPE.get(type_v, 2.0)
    return (k + v) / 1048576


@dataclass
class Estimate:
    gpu_layers: int
    total_layers: int
    weights_gpu_mb: float
    weights_cpu_mb: float
    kv_gpu_mb: float
    kv_cpu_mb: float
    overhead_gpu_mb: float
    runtime_cpu_mb: float

    @property
    def vram_mb(self) -> float:
        return self.weights_gpu_mb + self.kv_gpu_mb + self.overhead_gpu_mb

    @property
    def ram_mb(self) -> float:
        return self.weights_cpu_mb + self.kv_cpu_mb + self.runtime_cpu_mb


def estimate(info: GGUFInfo, load: LoadSettings, ngl: int, gpu_ok: bool, extra_gpu_mb: float = 0.0,
             extra_cpu_mb: float = 0.0) -> Estimate:
    n_layers = info.n_layers or 32
    total = n_layers + 1                      # + output layer
    ngl = max(0, min(ngl, total)) if gpu_ok else 0
    per = info.size_mb / total
    w_gpu = per * ngl
    kv = kv_cache_mb(info, load.n_ctx, load.cache_type_k, load.cache_type_v)
    kv_gpu = kv * min(ngl, n_layers) / n_layers
    over = (GPU_CONTEXT_MB + compute_buffer_mb(load.n_ubatch)) if ngl > 0 else 0.0
    if not gpu_ok:
        extra_cpu_mb += extra_gpu_mb
        extra_gpu_mb = 0.0
    return Estimate(ngl, total, w_gpu, info.size_mb - w_gpu, kv_gpu, kv - kv_gpu, over + extra_gpu_mb,
                    RUNTIME_MB + extra_cpu_mb)


def auto_gpu_layers(info: GGUFInfo, load: LoadSettings, vram_free_mb: float, margin_mb: float = 150) -> int:
    """How many layers fit into the given amount of free VRAM (weights + their KV cache + buffers)."""
    n_layers = info.n_layers or 32
    total = n_layers + 1
    budget = vram_free_mb - (GPU_CONTEXT_MB + compute_buffer_mb(load.n_ubatch) + margin_mb)
    if budget <= 0:
        return 0
    kv = kv_cache_mb(info, load.n_ctx, load.cache_type_k, load.cache_type_v)
    per_layer = info.size_mb / total + kv / n_layers
    return int(max(0, min(total, budget // per_layer)))


def suggest_defaults(info: GGUFInfo | None, vram_total_mb: int) -> LoadSettings:
    L = LoadSettings()
    if info and info.n_ctx_train:
        L.n_ctx = max(512, min(4096, info.n_ctx_train))
    if 0 < vram_total_mb <= 6144:
        L.n_ubatch = 128 if vram_total_mb <= 4608 else 256
    elif vram_total_mb >= 8192:
        L.n_ubatch, L.n_batch = 512, 1024
    return L
