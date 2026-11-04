"""LaTeX math -> Qt rich text (Unicode symbols, <sup>/<sub>, small tables). No dependencies."""
from __future__ import annotations

import html
import re

GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ", "eta": "η",
    "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π",
    "varpi": "ϖ", "rho": "ρ", "varrho": "ϱ", "sigma": "σ", "varsigma": "ς", "tau": "τ", "upsilon": "υ", "phi": "φ",
    "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω", "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ",
    "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}
# relations / binary operators get a little air around them
RELATIONS = {
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠", "approx": "≈", "equiv": "≡", "sim": "∼",
    "simeq": "≃", "cong": "≅", "propto": "∝", "ll": "≪", "gg": "≫", "to": "→", "rightarrow": "→", "leftarrow": "←",
    "leftrightarrow": "↔", "Rightarrow": "⇒", "Leftarrow": "⇐", "Leftrightarrow": "⇔", "implies": "⟹", "impliedby": "⟸",
    "iff": "⟺", "mapsto": "↦", "longrightarrow": "⟶", "longleftarrow": "⟵", "uparrow": "↑", "downarrow": "↓",
    "in": "∈", "notin": "∉", "ni": "∋", "subset": "⊂", "subseteq": "⊆", "supset": "⊃", "supseteq": "⊇",
    "times": "×", "div": "÷", "cdot": "·", "pm": "±", "mp": "∓", "ast": "∗", "star": "⋆", "circ": "∘", "oplus": "⊕",
    "otimes": "⊗", "cup": "∪", "cap": "∩", "setminus": "∖", "land": "∧", "wedge": "∧", "lor": "∨", "vee": "∨",
    "perp": "⊥", "parallel": "∥", "mid": "|", "lt": "<", "gt": ">", "lesssim": "≲", "gtrsim": "≳",
}
SYMBOLS = {
    "infty": "∞", "partial": "∂", "nabla": "∇", "sum": "∑", "prod": "∏", "coprod": "∐", "int": "∫", "iint": "∬",
    "iiint": "∭", "oint": "∮", "bigcup": "⋃", "bigcap": "⋂", "bigoplus": "⨁", "emptyset": "∅", "varnothing": "∅",
    "forall": "∀", "exists": "∃", "nexists": "∄", "neg": "¬", "lnot": "¬", "ldots": "…", "dots": "…", "cdots": "⋯",
    "vdots": "⋮", "ddots": "⋱", "bullet": "•", "angle": "∠", "triangle": "△", "therefore": "∴", "because": "∵",
    "hbar": "ℏ", "ell": "ℓ", "Re": "ℜ", "Im": "ℑ", "aleph": "ℵ", "prime": "′", "degree": "°", "dagger": "†",
    "langle": "⟨", "rangle": "⟩", "lfloor": "⌊", "rfloor": "⌋", "lceil": "⌈", "rceil": "⌉", "vert": "|", "Vert": "‖",
    "lbrace": "{", "rbrace": "}", "top": "⊤", "bot": "⊥", "checkmark": "✓", "square": "□", "Box": "□", "surd": "√",
}
FUNCS = {"sin", "cos", "tan", "cot", "sec", "csc", "sinh", "cosh", "tanh", "coth", "arcsin", "arccos", "arctan", "log",
         "ln", "lg", "exp", "lim", "liminf", "limsup", "max", "min", "sup", "inf", "det", "gcd", "arg", "deg", "dim",
         "ker", "mod", "Pr", "hom", "trace", "rank"}
ACCENTS = {"vec": "\u20d7", "hat": "\u0302", "widehat": "\u0302", "bar": "\u0304", "dot": "\u0307", "ddot": "\u0308",
           "tilde": "\u0303", "widetilde": "\u0303", "check": "\u030c", "acute": "\u0301", "grave": "\u0300"}
BLACKBOARD = {"R": "ℝ", "N": "ℕ", "Z": "ℤ", "Q": "ℚ", "C": "ℂ", "P": "ℙ", "H": "ℍ", "E": "𝔼", "F": "𝔽", "1": "𝟙"}
SKIP = {"left", "right", "bigl", "bigr", "Bigl", "Bigr", "big", "Big", "bigg", "Bigg", "displaystyle", "textstyle",
        "scriptstyle", "limits", "nolimits", "nonumber", "notag", "hline", "boldsymbol_"}
ESCAPES = {",": "\u2009", ";": "\u2004", ":": "\u2005", "!": "", " ": " ", "{": "{", "}": "}", "%": "%", "$": "$",
           "&": "&amp;", "#": "#", "_": "_", "|": "‖", "\\": "<br>", "/": "/", "-": "-", ">": "\u2005", "<": "&lt;"}
VULGAR = {("1", "2"): "½", ("1", "3"): "⅓", ("2", "3"): "⅔", ("1", "4"): "¼", ("3", "4"): "¾", ("1", "5"): "⅕",
          ("2", "5"): "⅖", ("3", "5"): "⅗", ("4", "5"): "⅘", ("1", "6"): "⅙", ("5", "6"): "⅚", ("1", "7"): "⅐",
          ("1", "8"): "⅛", ("3", "8"): "⅜", ("5", "8"): "⅝", ("7", "8"): "⅞", ("1", "9"): "⅑", ("1", "10"): "⅒"}
MATRIX = {"pmatrix": ("(", ")"), "bmatrix": ("[", "]"), "Bmatrix": ("{", "}"), "vmatrix": ("|", "|"),
          "Vmatrix": ("‖", "‖"), "matrix": ("", ""), "smallmatrix": ("", ""), "array": ("", "")}
ALIGNED = {"align", "align*", "aligned", "alignat", "gather", "gathered", "equation", "equation*", "split", "eqnarray",
           "eqnarray*", "multline", "multline*", "flalign"}
FONT = "font-family:'Cambria Math','STIX Two Math','Latin Modern Math','DejaVu Serif','Times New Roman',serif;"
THIN = "\u2009"


def _read_group(s: str, i: int) -> tuple[str, int]:
    """One LaTeX argument starting at s[i]: {...}, \\command or a single character."""
    n = len(s)
    while i < n and s[i] == " ":
        i += 1
    if i >= n:
        return "", i
    if s[i] == "{":
        depth, j = 0, i
        while j < n:
            if s[j] == "\\":
                j += 2
                continue
            if s[j] == "{":
                depth += 1
            elif s[j] == "}":
                depth -= 1
                if depth == 0:
                    return s[i + 1:j], j + 1
            j += 1
        return s[i + 1:], n
    if s[i] == "\\":
        j = i + 1
        while j < n and s[j].isalpha():
            j += 1
        if j == i + 1:
            j = min(n, i + 2)
        return s[i:j], j
    return s[i], i + 1


def _plain(arg: str) -> str:
    """Text content of a (simple) argument, used for \\text{...}."""
    return html.escape(re.sub(r"\\([A-Za-z]+|.)", lambda m: SYMBOLS.get(m.group(1), RELATIONS.get(m.group(1), GREEK.get(m.group(1), m.group(1)))), arg).replace("{", "").replace("}", ""))


def _env(name: str, body: str, display: bool) -> str:
    rows = [r for r in re.split(r"\\\\", body) if r.strip() != "" or len(r) > 0]
    rows = [r for r in rows if r.strip()]
    if name == "array":
        _spec, k = _read_group(body.strip(), 0)
        body2 = body.strip()[k:]
        rows = [r for r in re.split(r"\\\\", body2) if r.strip()]
    cells = [[_conv(c) for c in re.split(r"(?<!\\)&", r)] for r in rows]
    if not cells:
        return ""
    if not display and name in MATRIX:
        left, right = MATRIX[name]
        return left + "; ".join(THIN.join(r) for r in cells) + right
    if name == "cases":
        left, right, aligns = "{", "", ["left", "left"]
    elif name in MATRIX:
        (left, right), aligns = MATRIX[name], ["center"] * 20
    else:                                                   # align, gather, ...
        left, right, aligns = "", "", ["right", "left"] * 10
    trs = []
    for r in cells:
        tds = "".join('<td align="%s" style="padding:1px 8px;">%s</td>' % (aligns[k] if k < len(aligns) else "left", c)
                      for k, c in enumerate(r))
        trs.append("<tr>%s</tr>" % tds)
    inner = '<table cellspacing="0" cellpadding="1" align="center">%s</table>' % "".join(trs)
    if not left and not right:
        return inner
    big = '<td style="font-size:xx-large;">%s</td>'
    return ('<table cellspacing="0" cellpadding="0" align="center"><tr>%s<td>%s</td>%s</tr></table>'
            % (big % left, inner, big % right))


def _command(name: str, s: str, i: int, out: list, display: bool) -> int:
    n = len(s)
    if name in SKIP:
        if i < n and s[i] == ".":
            i += 1
        return i
    if name in ("frac", "dfrac", "tfrac", "cfrac"):
        a, i = _read_group(s, i)
        b, i = _read_group(s, i)
        pa, pb = a.strip(), b.strip()
        if (pa, pb) in VULGAR:
            out.append(VULGAR[(pa, pb)])
        else:
            out.append("<sup>%s</sup>⁄<sub>%s</sub>" % (_conv(a), _conv(b)))
        return i
    if name == "binom":
        a, i = _read_group(s, i)
        b, i = _read_group(s, i)
        out.append("(<sup>%s</sup><sub>%s</sub>)" % (_conv(a), _conv(b)))
        return i
    if name == "sqrt":
        idx = ""
        j = i
        while j < n and s[j] == " ":
            j += 1
        if j < n and s[j] == "[":
            k = s.find("]", j)
            if k != -1:
                idx, i = s[j + 1:k], k + 1
        a, i = _read_group(s, i)
        body = _conv(a)
        mark = {"": "√", "3": "∛", "4": "∜"}.get(idx.strip())
        prefix = mark if mark else "<sup>%s</sup>√" % _conv(idx)
        out.append(prefix + (body if len(a.strip()) <= 1 else "(%s)" % body))
        return i
    if name in ("text", "mathrm", "operatorname", "mbox", "textrm", "mathsf", "textit", "textnormal", "mathtt"):
        a, i = _read_group(s, i)
        out.append(_plain(a))
        return i
    if name in ("mathbf", "boldsymbol", "textbf", "bm", "pmb"):
        a, i = _read_group(s, i)
        out.append("<b>%s</b>" % _conv(a))
        return i
    if name == "mathbb":
        a, i = _read_group(s, i)
        out.append("".join(BLACKBOARD.get(ch, ch) for ch in a.strip()))
        return i
    if name in ("mathcal", "mathscr", "mathfrak", "mathit", "mathbfit"):
        a, i = _read_group(s, i)
        out.append(_conv(a))
        return i
    if name in ACCENTS:
        a, i = _read_group(s, i)
        a = a.strip()
        if re.fullmatch(r"[A-Za-z]", a):
            out.append("<i>%s%s</i>" % (a, ACCENTS[name]))
        elif a.startswith("\\") and a[1:] in GREEK:
            out.append(GREEK[a[1:]] + ACCENTS[name])
        else:
            body = _conv(a)
            out.append(body + ACCENTS[name])
        return i
    if name == "overline":
        a, i = _read_group(s, i)
        out.append('<span style="text-decoration:overline;">%s</span>' % _conv(a))
        return i
    if name in ("underline", "underbrace", "overbrace"):
        a, i = _read_group(s, i)
        out.append("<u>%s</u>" % _conv(a))
        return i
    if name in ("quad", "qquad"):
        out.append("\u2003" if name == "quad" else "\u2003\u2003")
        return i
    if name in ("label", "tag", "ref", "eqref", "color", "textcolor", "phantom", "hphantom", "vphantom"):
        _a, i = _read_group(s, i)
        if name == "textcolor":
            _b, i = _read_group(s, i)
        return i
    if name == "begin":
        env, i = _read_group(s, i)
        end = "\\end{%s}" % env
        k = s.find(end, i)
        body, i = (s[i:k], k + len(end)) if k != -1 else (s[i:], n)
        out.append(_env(env.strip(), body, display))
        return i
    if name in FUNCS:
        out.append("%s%s" % (name, THIN))
        return i
    if name in GREEK:
        out.append(GREEK[name])
        return i
    if name in RELATIONS:
        out.append(RELATIONS[name] if name == "mid" else THIN + html.escape(RELATIONS[name], quote=False) + THIN)
        return i
    if name in SYMBOLS:
        out.append(SYMBOLS[name])
        return i
    out.append(html.escape("\\" + name))
    return i


def _conv(s: str, display: bool = False) -> str:
    out: list[str] = []
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if ch == "\\":
            j = i + 1
            if j < n and s[j].isalpha():
                while j < n and s[j].isalpha():
                    j += 1
                i = _command(s[i + 1:j], s, j, out, display)
            else:
                sym = s[j] if j < n else ""
                out.append(ESCAPES.get(sym, html.escape(sym)))
                i = j + 1
        elif ch in "^_":
            arg, i = _read_group(s, i + 1)
            tag = "sup" if ch == "^" else "sub"
            if ch == "^" and arg.strip() in ("\\circ", "∘", "°"):
                out.append("°")
            elif ch == "^" and arg.strip() in ("\\prime", "'"):
                out.append("′")
            else:
                out.append("<%s>%s</%s>" % (tag, _conv(arg), tag))
        elif ch == "{":
            arg, i = _read_group(s, i)
            out.append(_conv(arg))
        elif ch.isascii() and ch.isalpha():
            j = i
            while j < n and s[j].isascii() and s[j].isalpha():
                j += 1
            out.append("<i>%s</i>" % s[i:j])
            i = j
        elif ch in "=<>":
            out.append(THIN + html.escape(ch) + THIN)
            i += 1
        elif ch in "+-":
            out.append(THIN + ("−" if ch == "-" else "+") + THIN)
            i += 1
        elif ch == "'":
            out.append("′")
            i += 1
        elif ch in " \t\r\n":
            i += 1
        else:
            out.append(html.escape(ch, quote=False))
            i += 1
    return "".join(out)


def render_math(src: str, display: bool = False) -> str:
    body = _conv(src.strip(), display)
    if display:
        return '<div align="center" style="margin:6px 0; font-size:large; %s">%s</div>' % (FONT, body)
    return '<span style="%s">%s</span>' % (FONT, body)
