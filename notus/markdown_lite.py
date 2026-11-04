"""Markdown -> Qt rich text: headings, nested lists, tables, code, quotes, links, strike-through and LaTeX math."""
from __future__ import annotations

import html
import re

from .mathtext import render_math

_FENCE = re.compile(r"```([^\n`]*)\n(.*?)(?:```|\Z)", re.S)
_DISPLAY = re.compile(r"\$\$(.+?)\$\$|\\\[(.+?)\\\]", re.S)
_INLINE_MATH = re.compile(r"\\\((.+?)\\\)|(?<![\\$\w])\$(?![\s$])([^$\n]+?)(?<![\s\\])\$(?![\d$])")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_STASH = re.compile("\x01([ID])(\\d+)\x01")


def render(text: str, c: dict) -> str:
    store: dict = {}
    out: list[str] = []
    pos = 0
    for m in _FENCE.finditer(text):
        out.append(_blocks(text[pos:m.start()], c, store))
        out.append(_code(m.group(1).strip(), m.group(2), c))
        pos = m.end()
    out.append(_blocks(text[pos:], c, store))
    return "".join(out)


def _code(lang: str, code: str, c: dict) -> str:
    body = html.escape(code.rstrip("\n"))
    label = ""
    if lang:
        label = '<div style="color:%s; font-size:small;">%s</div>' % (c["muted"], html.escape(lang))
    pre = '<pre style="margin:0; white-space:pre-wrap; color:%s; font-family:monospace;">%s</pre>' % (c["code_fg"], body)
    return ('<table width="100%%" cellspacing="0" cellpadding="8" style="margin:6px 0;"><tr>'
            '<td bgcolor="%s">%s%s</td></tr></table>') % (c["code_bg"], label, pre)


def _stash(store: dict, kind: str, value: str) -> str:
    key = len(store)
    store[(kind, key)] = value
    return "\x01%s%d\x01" % (kind, key)


def _unstash(s: str, store: dict) -> str:
    return _STASH.sub(lambda m: store.get((m.group(1), int(m.group(2))), ""), s)


def _inline(s: str, c: dict, store: dict) -> str:
    parts = re.split(r"(`[^`\n]+`)", s)
    out = []
    for i, p in enumerate(parts):
        if i % 2 == 1:
            out.append('<span style="background-color:%s; font-family:monospace;">&nbsp;%s&nbsp;</span>'
                       % (c["inline_bg"], html.escape(p[1:-1])))
            continue
        p = _INLINE_MATH.sub(lambda m: _stash(store, "I", render_math(m.group(1) or m.group(2), False)), p)
        e = html.escape(p, quote=False)
        e = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", e)
        e = re.sub(r"__(.+?)__", r"<b>\1</b>", e)
        e = re.sub(r"~~(.+?)~~", r"<s>\1</s>", e)
        e = re.sub(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])", r"<i>\1</i>", e)
        e = re.sub(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)", r"<i>\1</i>", e)
        e = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", r'<a href="\2">\1</a>', e)
        out.append(e)
    return _unstash("".join(out), store)


def _split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [x.strip().replace("\\|", "|") for x in re.split(r"(?<!\\)\|", s)]


def _table(header: list, aligns: list, rows: list, c: dict, store: dict) -> str:
    def cell(tag: str, text: str, k: int) -> str:
        al = aligns[k] if k < len(aligns) else "left"
        if tag == "th":
            return '<th align="%s" bgcolor="%s">%s</th>' % (al, c["inline_bg"], _inline(text, c, store))
        return '<td align="%s">%s</td>' % (al, _inline(text, c, store))

    ncols = len(header)
    out = ['<table border="1" cellspacing="0" cellpadding="6" style="margin:6px 0;">']
    out.append("<tr>%s</tr>" % "".join(cell("th", h, k) for k, h in enumerate(header)))
    for r in rows:
        r = (r + [""] * ncols)[:ncols]
        out.append("<tr>%s</tr>" % "".join(cell("td", x, k) for k, x in enumerate(r)))
    out.append("</table>")
    return "".join(out)


def _blocks(text: str, c: dict, store: dict) -> str:
    text = _DISPLAY.sub(lambda m: "\n" + _stash(store, "D", render_math(m.group(1) or m.group(2), True)) + "\n", text)
    lines = text.split("\n")
    out: list[str] = []
    para: list[str] = []
    stack: list[tuple[int, str]] = []          # open lists: (indent, tag)
    sizes = {1: "x-large", 2: "large", 3: "large", 4: "medium"}

    def end_para() -> None:
        if para:
            out.append("<p style='margin:4px 0;'>" + "<br>".join(_inline(x, c, store) for x in para) + "</p>")
            para.clear()

    def close_to(indent: int) -> None:
        while stack and stack[-1][0] > indent:
            out.append("</li></%s>" % stack.pop()[1])

    def end_list() -> None:
        close_to(-1)

    def add_item(indent: int, tag: str, body: str) -> None:
        close_to(indent)
        if stack and stack[-1][0] == indent:
            if stack[-1][1] != tag:
                out.append("</li></%s>" % stack.pop()[1])
            else:
                out.append("</li>")
        if not stack or stack[-1][0] < indent:
            out.append("<%s style='margin:2px 0;'>" % tag)
            stack.append((indent, tag))
        body = re.sub(r"^\[ \]\s+", "☐ ", body)
        body = re.sub(r"^\[[xX]\]\s+", "☑ ", body)
        out.append("<li>%s" % _inline(body, c, store))

    i = 0
    while i < len(lines):
        raw = lines[i].replace("\t", "    ")
        s = raw.strip()
        i += 1
        if not s:
            end_para(); end_list()
            continue
        if re.fullmatch("\x01D\\d+\x01", s):
            end_para(); end_list()
            out.append(store[("D", int(s[2:-1]))])
            continue
        # table: header line + separator line
        if "|" in s and i < len(lines) and _TABLE_SEP.match(lines[i]) and "-" in lines[i]:
            end_para(); end_list()
            header = _split_row(s)
            aligns = []
            for sep in _split_row(lines[i]):
                aligns.append("center" if sep.startswith(":") and sep.endswith(":") else "right" if sep.endswith(":") else "left")
            i += 1
            rows = []
            while i < len(lines) and lines[i].strip() and "|" in lines[i]:
                rows.append(_split_row(lines[i]))
                i += 1
            out.append(_table(header, aligns, rows, c, store))
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            end_para(); end_list()
            out.append("<p style='margin:8px 0 2px 0; font-size:%s; font-weight:600;'>%s</p>"
                       % (sizes[len(m.group(1))], _inline(m.group(2), c, store)))
            continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", s):
            end_para(); end_list()
            out.append("<hr>")
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        m = re.match(r"^[-*+]\s+(.*)$", s)
        if m:
            end_para(); add_item(indent, "ul", m.group(1))
            continue
        m = re.match(r"^\d+[.)]\s+(.*)$", s)
        if m:
            end_para(); add_item(indent, "ol", m.group(1))
            continue
        m = re.match(r"^>\s?(.*)$", s)
        if m:
            end_para(); end_list()
            out.append("<p style='margin:4px 0 4px 12px; color:%s;'>%s</p>" % (c["muted"], _inline(m.group(1), c, store)))
            continue
        if stack and indent > stack[-1][0]:      # continuation line of a list item
            out.append("<br>" + _inline(s, c, store))
            continue
        end_list()
        para.append(s)
    end_para(); end_list()
    return "".join(out)
