"""Reading files and images the user attaches to a message."""
from __future__ import annotations

import base64
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

TEXT_EXT = {
    ".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".json", ".jsonl", ".xml", ".yaml", ".yml", ".toml", ".ini",
    ".cfg", ".conf", ".log", ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".kt", ".c", ".h", ".cpp", ".hpp", ".cs",
    ".go", ".rs", ".rb", ".php", ".sh", ".bat", ".ps1", ".sql", ".html", ".htm", ".css", ".gradle", ".properties",
    ".srt", ".tex",
}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
DOC_EXT = {".pdf", ".docx"}
MAX_READ_BYTES = 30 * 1024 * 1024


class AttachmentError(Exception):
    pass


def kind_of(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in TEXT_EXT or ext in DOC_EXT:
        return "file"
    return "unknown"


def _docx_text(path: str) -> str:
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(path) as z:
        root = ElementTree.fromstring(z.read("word/document.xml"))
    paras = []
    for p in root.iter(ns + "p"):
        paras.append("".join(t.text or "" for t in p.iter(ns + "t")))
    return "\n".join(paras)


def _pdf_text(path: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise AttachmentError("PDF support needs the 'pypdf' package") from e
    reader = PdfReader(path)
    pages = []
    for i, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append("--- page %d ---\n%s" % (i, text))
    return "\n\n".join(pages)


def read_document(path: str, max_chars: int) -> tuple[str, bool]:
    """Text of a file and whether it was truncated. Raises AttachmentError for unreadable files."""
    p = Path(path)
    try:
        if p.stat().st_size > MAX_READ_BYTES:
            raise AttachmentError("file is larger than 30 MB")
        ext = p.suffix.lower()
        if ext == ".docx":
            text = _docx_text(path)
        elif ext == ".pdf":
            text = _pdf_text(path)
        else:
            raw = p.read_bytes()
            if b"\x00" in raw[:4096]:
                raise AttachmentError("looks like a binary file")
            text = raw.decode("utf-8", "replace")
    except (OSError, zipfile.BadZipFile, KeyError, ElementTree.ParseError) as e:
        raise AttachmentError(str(e)) from e
    except AttachmentError:
        raise
    except Exception as e:                       # pypdf can raise many different errors on broken files
        raise AttachmentError(str(e)) from e
    text = re.sub(r"\n{4,}", "\n\n\n", text).strip()
    if not text:
        raise AttachmentError("no text found (scanned PDF? attach it as images instead)")
    if len(text) > max_chars:
        return text[:max_chars], True
    return text, False


def image_to_data_url(path: str, max_side: int = 1024, quality: int = 85) -> str:
    """Load an image, shrink it (old hardware: fewer image tokens) and return a JPEG data URL."""
    from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PyQt6.QtGui import QImage

    img = QImage(path)
    if img.isNull():
        raise AttachmentError("cannot read the image")
    return qimage_to_data_url(img, max_side, quality)


def qimage_to_data_url(img, max_side: int = 1024, quality: int = 85) -> str:
    from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PyQt6.QtGui import QImage

    if max(img.width(), img.height()) > max_side:
        img = img.scaled(max_side, max_side, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.convertToFormat(QImage.Format.Format_RGB32).save(buf, "JPG", quality)
    return "data:image/jpeg;base64," + base64.b64encode(bytes(ba)).decode("ascii")


def find_mmproj(model_path: str) -> str:
    """Look for a vision projector next to the model (mmproj-*.gguf). Returns '' if none."""
    folder = Path(model_path).parent
    try:
        cands = [p for p in folder.glob("*.gguf") if "mmproj" in p.name.lower()]
    except OSError:
        return ""
    if not cands:
        return ""
    stem = Path(model_path).stem.lower()
    prefix = re.split(r"[-_.]?(?:q\d|iq\d|f16|bf16|f32)", stem)[0]

    def score(p: Path) -> tuple:
        n = p.name.lower()
        return (prefix and prefix in n, "f16" in n or "bf16" in n, -p.stat().st_size)

    return str(max(cands, key=score))
