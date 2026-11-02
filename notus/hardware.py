"""Hardware detection (CPU / RAM / NVIDIA GPU). No Qt imports."""
from __future__ import annotations

import copy
import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field

import psutil

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class GPU:
    index: int
    name: str
    total_mb: int
    used_mb: int
    free_mb: int
    cc: str = ""
    dev_id: str = ""          # backend device id, e.g. Vulkan0 (empty for nvidia-smi entries)


@dataclass
class Hardware:
    cpu_name: str = "CPU"
    cores_physical: int = 1
    cores_logical: int = 1
    ram_total_mb: int = 0
    ram_free_mb: int = 0
    gpus: list = field(default_factory=list)
    avx: bool | None = None
    avx2: bool | None = None

    @property
    def vram_total_mb(self) -> int:
        return self.gpus[0].total_mb if self.gpus else 0

    @property
    def vram_free_mb(self) -> int:
        return self.gpus[0].free_mb if self.gpus else 0


def _nvidia_smi() -> str | None:
    p = shutil.which("nvidia-smi")
    if p:
        return p
    if os.name == "nt":
        for cand in (
            r"C:\Windows\System32\nvidia-smi.exe",
            r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
        ):
            if os.path.isfile(cand):
                return cand
    return None


def query_gpus() -> list[GPU]:
    exe = _nvidia_smi()
    if not exe:
        return []
    out = None
    for cols in ("name,memory.total,memory.used,memory.free,compute_cap", "name,memory.total,memory.used,memory.free"):
        try:
            out = subprocess.run(
                [exe, f"--query-gpu={cols}", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=8, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        if out.returncode == 0 and out.stdout.strip():
            break
        out = None
    if out is None:
        return []
    gpus: list[GPU] = []
    for i, line in enumerate(out.stdout.strip().splitlines()):
        parts = [x.strip() for x in line.split(",")]
        try:
            gpus.append(GPU(i, parts[0], int(float(parts[1])), int(float(parts[2])),
                            int(float(parts[3])), parts[4] if len(parts) > 4 else ""))
        except (ValueError, IndexError):
            continue
    return gpus


_DEV_RE = re.compile(r"^\s*([A-Za-z][\w-]*\d+):\s*(.+?)\s*\((\d+)\s*MiB,\s*(\d+)\s*MiB free\)\s*$")
_SOFTWARE = re.compile(r"llvmpipe|lavapipe|swiftshader|basic render", re.I)
_INTEGRATED = re.compile(
    r"UHD|Iris|HD Graphics|Intel\(R\) Graphics|Radeon\(TM\) Graphics|Radeon Graphics|Vega ?(3|6|7|8|10|11)\b", re.I)


def parse_devices(text: str) -> list[GPU]:
    """Parse `llama-server --list-devices` (works for Vulkan, CUDA, HIP ... on any vendor)."""
    out: list[GPU] = []
    for line in text.splitlines():
        m = _DEV_RE.match(line)
        if not m or _SOFTWARE.search(m.group(2)):
            continue
        total, free = int(m.group(3)), int(m.group(4))
        out.append(GPU(len(out), m.group(2), total, max(0, total - free), free, "", m.group(1)))
    return out


def pick_device(devices: list, choice: str = "auto"):
    """Selected compute device, or None for CPU-only. 'auto' prefers a discrete card over an iGPU."""
    if choice == "cpu" or not devices:
        return None
    if choice not in ("", "auto"):
        for d in devices:
            if d.dev_id == choice:
                return d
    return max(devices, key=lambda d: d.total_mb - (1_000_000 if _INTEGRATED.search(d.name) else 0))


def _cpu_name() -> str:
    try:
        if os.name == "nt":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or "CPU"


def _cpu_features() -> tuple[bool | None, bool | None]:
    try:
        if os.name == "nt":
            import ctypes
            f = ctypes.windll.kernel32.IsProcessorFeaturePresent
            return bool(f(39)), bool(f(40))   # PF_AVX_..., PF_AVX2_...
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("flags"):
                    flags = set(line.split(":", 1)[1].split())
                    return "avx" in flags, "avx2" in flags
    except Exception:
        pass
    return None, None


def detect_hardware() -> Hardware:
    vm = psutil.virtual_memory()
    avx, avx2 = _cpu_features()
    return Hardware(
        cpu_name=_cpu_name(),
        cores_physical=psutil.cpu_count(logical=False) or psutil.cpu_count() or 1,
        cores_logical=psutil.cpu_count() or 1,
        ram_total_mb=int(vm.total // 1048576),
        ram_free_mb=int(vm.available // 1048576),
        gpus=query_gpus(),
        avx=avx, avx2=avx2,
    )


def snapshot(static: Hardware) -> Hardware:
    """Fresh copy of `static` with up-to-date free RAM / VRAM."""
    hw = copy.copy(static)
    hw.ram_free_mb = int(psutil.virtual_memory().available // 1048576)
    hw.gpus = query_gpus()
    return hw
