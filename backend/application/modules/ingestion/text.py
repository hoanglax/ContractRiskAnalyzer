"""Canonical text forms shared by ingest, detection and the gate.

Two functions, on purpose (INGEST_PLAN.md §3):

  clean(s)  document text. Keeps line structure (the segmenter anchors on line
            starts, humans read it). Ingest emits this; it is `Document.text`.
  norm(s)   comparison form only. clean + fold typography + collapse ALL
            whitespace to one space, so a quote that wraps across lines still
            matches. Never shown, never stored as the document.

find_span(text, span) locates a quote in clean text via norm and returns
offsets in the *clean* text, for highlighting.

Deliberately NOT folded: Vietnamese tone-mark placement (hoà / hòa) and
Đ (U+0110) vs Ð (U+00D0). If the model "corrects" those, it rewrote the
contract and the gate should say so.
"""
import re
import unicodedata

# Line separators other than \n.
_NEWLINES = {"\r\n": "\n", "\r": "\n", " ": "\n", " ": "\n",
             "\x0b": "\n", "\x0c": "\n", "\x85": "\n"}
_NEWLINE_RE = re.compile("|".join(map(re.escape, _NEWLINES)))

# Unicode spaces -> plain space.
_SPACES = dict.fromkeys(
    map(ord, "\t         "
             "      　"), " ")

_MULTISPACE = re.compile(r" {2,}")
_MULTIBLANK = re.compile(r"\n{3,}")

# Typography folds for norm(). Each maps one char to a string; the offset map
# in _norm_map points every output char back at its single source char.
_FOLD = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
    "―": "-", "−": "-",
    "…": "...",
}


def clean(s: str) -> str:
    """Document text: NFC, unified newlines/spaces, no invisibles or control
    chars, runs of spaces collapsed, lines stripped, at most one blank line.

    Invisible = Unicode category Cf (zero-width chars, BOM, soft hyphen, word
    joiner, bidi marks like U+200E) — they survive copy-paste but not
    rendering, so a PDF of the same text would not contain them."""
    s = unicodedata.normalize("NFC", s)
    s = _NEWLINE_RE.sub(lambda m: _NEWLINES[m.group()], s)
    s = s.translate(_SPACES)
    s = "".join(c for c in s if c == "\n" or unicodedata.category(c) not in ("Cc", "Cf"))
    lines = (_MULTISPACE.sub(" ", ln).strip() for ln in s.split("\n"))
    return _MULTIBLANK.sub("\n\n", "\n".join(lines)).strip("\n")


def _norm_map(s: str) -> tuple[str, list[int]]:
    """norm() of already-clean text plus, for each output char, its index in s."""
    out, pos = [], []
    pending_space = False
    for i, c in enumerate(s):
        if c.isspace():
            pending_space = bool(out)          # no leading space
            continue
        if pending_space:
            out.append(" ")
            pos.append(i - 1)                  # the whitespace just before c
            pending_space = False
        f = _FOLD.get(c, c)
        out.append(f)
        pos.extend([i] * len(f))
    return "".join(out), pos


def norm(s: str) -> str:
    """Comparison form: clean, fold quotes/dashes/ellipsis, all whitespace -> one space."""
    return _norm_map(clean(s))[0]


# Form-filler characters: blanks to fill in ("Ông/Bà:……", "____"), not garbage.
_FILLER = set(".…_-–—*·:/,")


def readable_ratio(s: str) -> float:
    """Share of non-whitespace, non-filler characters that are letters or digits.

    Filler is excluded because form pages are mostly dotted blanks: with it
    counted, a real template page scored 0.27. Without it, real pages score
    >= 0.935 and whole contracts >= 0.978 (352 rendered pages, 100 templates),
    while bytes rendered as text (LibreOffice importing a broken .doc:
    "ÐÏ#à¡±#á###…") score ~0.01. Only filler, or nothing, scores 1.0 / 0.0."""
    ns = [c for c in s if not c.isspace()]
    if not ns:
        return 0.0
    content = [c for c in ns if c not in _FILLER]
    if not content:
        return 1.0
    return sum(unicodedata.category(c)[0] in "LN" for c in content) / len(content)


_TONES = set("̣̀́̃̉")    # huyền sắc ngã hỏi nặng
_WORD = re.compile(r"\w+")


def implausible_words(s: str) -> tuple[list[str], int]:
    """Words that cannot be Vietnamese, among words carrying Vietnamese marks.

    A Vietnamese syllable has at most one tone mark, one circumflex, one breve,
    and not both; "ươ" is the only double horn. A PDF whose font maps glyphs to
    the wrong characters produces text that is all letters (so readable_ratio
    passes) but breaks these rules: "Dàtà Enginêêr" for "Data Engineer".
    Words glued by removed spaces ("nhàTổ") also count, which is why the
    threshold sits well above zero. Returns (implausible words, marked words)."""
    bad, marked = [], 0
    for w in _WORD.findall(s):
        d = unicodedata.normalize("NFD", w.lower())
        tones = sum(c in _TONES for c in d)
        circ, breve, horn = d.count("̂"), d.count("̆"), d.count("̛")
        if tones or circ or breve or horn or "đ" in d:
            marked += 1
            if tones > 1 or circ > 1 or breve > 1 or horn > 2 or (circ and breve):
                bad.append(w)
    return bad, marked


def find_span(text: str, span: str, start: int = 0) -> tuple[int, int] | None:
    """Locate `span` in clean `text` under norm(); return (start, end) offsets
    into `text`, or None. `text` must already be clean() (Document.text is).
    `start` is an offset into `text` to search from."""
    needle = norm(span)
    if not needle:
        return None
    hay, pos = _norm_map(text)
    j0 = next((j for j, p in enumerate(pos) if p >= start), len(hay))
    j = hay.find(needle, j0)
    if j < 0:
        return None
    return pos[j], pos[j + len(needle) - 1] + 1
