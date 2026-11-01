"""Tiny Markdown -> Qt rich-text converter (headings, lists, code, bold/italic, links)."""
from __future__ import annotations

import html
import re

_FENCE = re.compile(r"```([^\n`]*)\n(.*?)(?:```|\Z)", re.S)


def render(text: str, c: dict) -> str:
    out: list[str] = []
    pos = 0
    for m in _FENCE.finditer(text):
        out.append(_blocks(text[pos:m.start()], c))
        out.append(_code(m.group(1).strip(), m.group(2), c))
        pos = m.end()
    out.append(_blocks(text[pos:], c))
    return "".join(out)


def _code(lang: str, code: str, c: dict) -> str:
    body = html.escape(code.rstrip("\n"))
    label = ""
    if lang:
        label = '<div style="color:%s; font-size:small;">%s</div>' % (c["muted"], html.escape(lang))
    pre = '<pre style="margin:0; white-space:pre-wrap; color:%s; font-family:monospace;">%s</pre>' % (c["code_fg"], body)
    return ('<table width="100%%" cellspacing="0" cellpadding="8" style="margin:6px 0;"><tr>'
            '<td bgcolor="%s">%s%s</td></tr></table>') % (c["code_bg"], label, pre)


def _inline(s: str, c: dict) -> str:
    parts = re.split(r"(`[^`\n]+`)", s)
    out = []
    for i, p in enumerate(parts):
        if i % 2 == 1:
            out.append('<span style="background-color:%s; font-family:monospace;">&nbsp;%s&nbsp;</span>'
                       % (c["inline_bg"], html.escape(p[1:-1])))
            continue
        e = html.escape(p, quote=False)
        e = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", e)
        e = re.sub(r"__(.+?)__", r"<b>\1</b>", e)
        e = re.sub(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])", r"<i>\1</i>", e)
        e = re.sub(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)", r"<i>\1</i>", e)
        e = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", r'<a href="\2">\1</a>', e)
        out.append(e)
    return "".join(out)


def _blocks(text: str, c: dict) -> str:
    out: list[str] = []
    para: list[str] = []
    items: list[str] = []
    kind = None

    def end_para() -> None:
        if para:
            out.append("<p style='margin:4px 0;'>" + "<br>".join(_inline(x, c) for x in para) + "</p>")
            para.clear()

    def end_list() -> None:
        nonlocal kind
        if items:
            tag = kind or "ul"
            out.append("<%s style='margin:4px 0;'>%s</%s>" % (tag, "".join("<li>%s</li>" % _inline(i, c) for i in items), tag))
            items.clear()
        kind = None

    sizes = {1: "x-large", 2: "large", 3: "large", 4: "medium"}
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            end_para(); end_list()
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            end_para(); end_list()
            out.append("<p style='margin:8px 0 2px 0; font-size:%s; font-weight:600;'>%s</p>"
                       % (sizes[len(m.group(1))], _inline(m.group(2), c)))
            continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", s):
            end_para(); end_list()
            out.append("<hr>")
            continue
        m = re.match(r"^[-*+]\s+(.*)$", s)
        if m:
            end_para()
            if kind not in (None, "ul"):
                end_list()
            kind = "ul"; items.append(m.group(1))
            continue
        m = re.match(r"^\d+[.)]\s+(.*)$", s)
        if m:
            end_para()
            if kind not in (None, "ol"):
                end_list()
            kind = "ol"; items.append(m.group(1))
            continue
        m = re.match(r"^>\s?(.*)$", s)
        if m:
            end_para(); end_list()
            out.append("<p style='margin:4px 0 4px 12px; color:%s;'>%s</p>" % (c["muted"], _inline(m.group(1), c)))
            continue
        end_list()
        para.append(s)
    end_para(); end_list()
    return "".join(out)
