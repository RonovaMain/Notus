"""Minimal GGUF header reader: metadata only, tensors are never touched."""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path


class GGUFError(Exception):
    pass


class _ArrayLen:
    """Placeholder for a skipped (large) array."""
    __slots__ = ("n",)

    def __init__(self, n: int) -> None:
        self.n = n


_FMT = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i", 6: "f", 7: "?", 10: "Q", 11: "q", 12: "d"}
_SIZE = {t: struct.calcsize("<" + c) for t, c in _FMT.items()}
_U64 = struct.Struct("<Q")

FILE_TYPES = {
    0: "F32", 1: "F16", 2: "Q4_0", 3: "Q4_1", 7: "Q8_0", 8: "Q5_0", 9: "Q5_1", 10: "Q2_K",
    11: "Q3_K_S", 12: "Q3_K_M", 13: "Q3_K_L", 14: "Q4_K_S", 15: "Q4_K_M", 16: "Q5_K_S",
    17: "Q5_K_M", 18: "Q6_K", 19: "IQ2_XXS", 20: "IQ2_XS", 21: "Q2_K_S", 22: "IQ3_XS",
    23: "IQ3_XXS", 24: "IQ1_S", 25: "IQ4_NL", 26: "IQ3_S", 27: "IQ3_M", 28: "IQ2_S",
    29: "IQ2_M", 30: "IQ4_XS", 31: "IQ1_M", 32: "BF16",
}
_QUANT_RE = re.compile(r"(IQ\d_[A-Z]+|Q\d_K_[SML]|Q\d_K|Q\d_\d|BF16|F16|F32)", re.I)
_SHARD_RE = re.compile(r"^(.*)-(\d{5})-of-(\d{5})\.gguf$", re.I)


@dataclass
class GGUFInfo:
    path: str
    size_bytes: int
    arch: str = "?"
    name: str = ""
    n_layers: int = 0
    n_ctx_train: int = 0
    n_embd: int = 0
    n_head: int = 0
    n_head_kv: int = 0
    key_length: int = 0
    value_length: int = 0
    n_vocab: int = 0
    n_experts: int = 0
    quant: str = ""
    has_chat_template: bool = False

    @property
    def size_mb(self) -> float:
        return self.size_bytes / 1048576


def _u32(f) -> int:
    raw = f.read(4)
    if len(raw) != 4:
        raise GGUFError("truncated file")
    return struct.unpack("<I", raw)[0]


def _u64(f) -> int:
    raw = f.read(8)
    if len(raw) != 8:
        raise GGUFError("truncated file")
    return _U64.unpack(raw)[0]


def _read_value(f, vtype: int, keep: bool):
    if vtype in _FMT:
        raw = f.read(_SIZE[vtype])
        if len(raw) != _SIZE[vtype]:
            raise GGUFError("truncated file")
        return struct.unpack("<" + _FMT[vtype], raw)[0] if keep else None
    if vtype == 8:
        n = _u64(f)
        if keep and n <= 65536:
            return f.read(n).decode("utf-8", "replace")
        f.seek(n, 1)
        return None
    if vtype == 9:
        et = _u32(f)
        n = _u64(f)
        if et in _FMT:
            size = _SIZE[et]
            if keep and n <= 1024:
                return list(struct.unpack(f"<{n}{_FMT[et]}", f.read(n * size)))
            f.seek(n * size, 1)
        elif et == 8:
            rd, sk = f.read, f.seek
            for _ in range(n):
                sk(_U64.unpack(rd(8))[0], 1)
        else:
            for _ in range(n):
                _read_value(f, et, False)
        return _ArrayLen(n)
    raise GGUFError(f"unknown value type {vtype}")


def _wanted(key: str) -> bool:
    return (
        key.startswith("general.")
        or key == "tokenizer.chat_template"
        or ".attention." in key
        or key.endswith((".block_count", ".context_length", ".embedding_length", ".expert_count"))
    )


def _total_size(p: Path) -> int:
    m = _SHARD_RE.match(p.name)
    if m:
        total = 0
        for sib in p.parent.glob(f"{m.group(1)}-*-of-{m.group(3)}.gguf"):
            try:
                total += sib.stat().st_size
            except OSError:
                pass
        if total:
            return total
    return p.stat().st_size


def read_gguf(path) -> GGUFInfo:
    p = Path(path)
    try:
        size = _total_size(p)
        meta: dict = {}
        with open(p, "rb") as f:
            if f.read(4) != b"GGUF":
                raise GGUFError("not a GGUF file")
            version = _u32(f)
            if version not in (2, 3):
                raise GGUFError(f"unsupported GGUF version {version}")
            _u64(f)                      # tensor count
            kv_count = _u64(f)
            if kv_count > 100_000:
                raise GGUFError("corrupt header")
            for _ in range(kv_count):
                klen = _u64(f)
                if klen > 1024:
                    raise GGUFError("corrupt header")
                key = f.read(klen).decode("utf-8", "replace")
                vtype = _u32(f)
                keep = _wanted(key)
                val = _read_value(f, vtype, keep)
                if keep or key == "tokenizer.ggml.tokens":
                    meta[key] = val
    except (OSError, struct.error) as e:
        raise GGUFError(str(e)) from e

    arch = str(meta.get("general.architecture", "") or "?")

    def g(suffix: str, default: int = 0) -> int:
        v = meta.get(f"{arch}.{suffix}", default)
        if isinstance(v, list):
            v = max(v) if v else default
        if v is None or isinstance(v, _ArrayLen):
            return default
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    n_head = g("attention.head_count")
    toks = meta.get("tokenizer.ggml.tokens")
    n_vocab = toks.n if isinstance(toks, _ArrayLen) else (len(toks) if isinstance(toks, list) else 0)

    quant = ""
    ft = meta.get("general.file_type")
    if isinstance(ft, int):
        quant = FILE_TYPES.get(ft, "")
    if not quant:
        m = _QUANT_RE.search(p.name)
        quant = m.group(1).upper() if m else ""

    name = meta.get("general.name")
    return GGUFInfo(
        path=str(p), size_bytes=size, arch=arch,
        name=name if isinstance(name, str) else "",
        n_layers=g("block_count"), n_ctx_train=g("context_length"), n_embd=g("embedding_length"),
        n_head=n_head, n_head_kv=g("attention.head_count_kv", n_head),
        key_length=g("attention.key_length"), value_length=g("attention.value_length"),
        n_vocab=n_vocab, n_experts=g("expert_count"), quant=quant,
        has_chat_template="tokenizer.chat_template" in meta,
    )


def is_first_shard_or_single(p: Path) -> bool:
    m = _SHARD_RE.match(p.name)
    return m is None or m.group(2) == "00001"
