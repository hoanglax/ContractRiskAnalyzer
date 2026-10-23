"""docx -> lines of text, stdlib only (INGEST_PLAN.md §4 docx, §7.1).

Reads word/document.xml in document order:
  paragraphs   one line each; w:br/w:cr inside a paragraph -> newline
  tables       one line per row, non-empty cells joined with " | "
  revisions    the accept-all view: w:ins / w:moveTo kept, w:del / w:moveFrom dropped
  fields       result text only (w:instrText is never read)
  text boxes   emitted as lines right after the paragraph that anchors them
  hidden text  (w:vanish) dropped — it is not what the parties see
  numbering    Word auto-numbering is not in the text; it is reconstructed from
               numbering.xml + styles.xml so "Điều 1." / "1.1" headings survive
Headers, footers, footnotes and comments are not part of the body and are skipped.
Anything skipped or reconstructed is counted and reported as a warning.
"""
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"


def q(tag: str) -> str:
    return f"{{{W}}}{tag}"


def local(el) -> str:
    return el.tag.rsplit("}", 1)[-1]


def wval(el, attr: str = "val"):
    return None if el is None else el.get(q(attr))


def _on(el) -> bool:
    """Boolean toggle property (w:vanish, w:isLgl): present and not false."""
    return el is not None and wval(el) not in ("0", "false", "off")


# ---------------- numbering ----------------

@dataclass
class Level:
    start: int = 1
    fmt: str = "decimal"
    text: str = "%1."
    restart: int | None = None     # w:lvlRestart; None = restart after any higher level
    legal: bool = False            # w:isLgl: render all levels as decimal
    suff: str = "tab"
    style: str | None = None       # w:pStyle: style linked to this level


def _parse_level(el) -> Level:
    lv = Level()
    if (s := wval(el.find(q("start")))) is not None:
        lv.start = int(s)
    if (f := wval(el.find(q("numFmt")))) is not None:
        lv.fmt = f
    if (t := el.find(q("lvlText"))) is not None:
        lv.text = wval(t) or ""
    if (r := wval(el.find(q("lvlRestart")))) is not None:
        lv.restart = int(r)
    lv.legal = _on(el.find(q("isLgl")))
    if (s := wval(el.find(q("suff")))) is not None:
        lv.suff = s
    lv.style = wval(el.find(q("pStyle")))
    return lv


def _roman(n: int) -> str:
    out = ""
    for v, s in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
                 (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out, n = out + s, n - v
    return out


def _letter(n: int) -> str:
    # Word: a..z, then aa, bb, ... (the letter repeats; it is not base-26)
    return chr(ord("a") + (n - 1) % 26) * ((n - 1) // 26 + 1) if n > 0 else ""


class Numbering:
    """Word list numbering: numId/ilvl on a paragraph -> its visible label."""

    def __init__(self, numbering_xml: bytes | None, styles_xml: bytes | None):
        self.abstract: dict[str, dict[int, Level]] = {}
        self.style_link: dict[str, str] = {}          # abstractNumId -> numStyleLink style
        self.nums: dict[str, tuple[str, dict[int, int], dict[int, Level]]] = {}
        self.styles: dict[str, tuple[str | None, str | None, int | None]] = {}
        self.counters: dict[str, list[int | None]] = {}
        self.seen_nums: set[str] = set()
        self.unknown_formats: set[str] = set()
        self.used = 0

        if styles_xml:
            for st in ET.fromstring(styles_xml).iter(q("style")):
                np_ = st.find(f"{q('pPr')}/{q('numPr')}")
                ilvl = wval(np_.find(q("ilvl"))) if np_ is not None else None
                self.styles[st.get(q("styleId"))] = (
                    wval(st.find(q("basedOn"))),
                    wval(np_.find(q("numId"))) if np_ is not None else None,
                    int(ilvl) if ilvl is not None else None)
        if numbering_xml:
            root = ET.fromstring(numbering_xml)
            for an in root.iter(q("abstractNum")):
                aid = an.get(q("abstractNumId"))
                self.abstract[aid] = {int(lv.get(q("ilvl"))): _parse_level(lv)
                                      for lv in an.findall(q("lvl"))}
                if (link := wval(an.find(q("numStyleLink")))) is not None:
                    self.style_link[aid] = link
            for n in root.iter(q("num")):
                starts, lvls = {}, {}
                for ov in n.findall(q("lvlOverride")):
                    il = int(ov.get(q("ilvl")))
                    if (s := wval(ov.find(q("startOverride")))) is not None:
                        starts[il] = int(s)
                    if (lv := ov.find(q("lvl"))) is not None:
                        lvls[il] = _parse_level(lv)
                self.nums[n.get(q("numId"))] = (wval(n.find(q("abstractNumId"))), starts, lvls)

    def _abstract_id(self, num_id: str, depth: int = 0) -> str | None:
        if num_id not in self.nums:
            return None
        aid = self.nums[num_id][0]
        # numStyleLink: this definition only points at a style that carries the real list
        if aid in self.style_link and depth < 5:
            linked = self._style_numpr(self.style_link[aid])[0]
            if linked and linked != num_id:
                return self._abstract_id(linked, depth + 1) or aid
        return aid

    def _style_numpr(self, style_id: str | None) -> tuple[str | None, int | None]:
        for _ in range(20):                       # basedOn chain, cycle-safe
            if style_id not in self.styles:
                return None, None
            based, num_id, ilvl = self.styles[style_id]
            if num_id is not None:
                return num_id, ilvl
            style_id = based
        return None, None

    def _level(self, num_id: str, aid: str, ilvl: int) -> Level:
        over = self.nums[num_id][2]
        return over.get(ilvl) or self.abstract.get(aid, {}).get(ilvl) or Level()

    def _fmt(self, n: int, fmt: str) -> str:
        if fmt == "decimal":
            return str(n)
        if fmt == "decimalZero":
            return f"{n:02d}"
        if fmt == "upperRoman":
            return _roman(n)
        if fmt == "lowerRoman":
            return _roman(n).lower()
        if fmt == "upperLetter":
            return _letter(n).upper()
        if fmt == "lowerLetter":
            return _letter(n)
        if fmt == "none":
            return ""
        self.unknown_formats.add(fmt)
        return str(n)

    def label(self, ppr) -> str | None:
        """Visible label for a paragraph (its w:pPr), advancing the counters; None if unnumbered."""
        if ppr is None:
            return None
        style = wval(ppr.find(q("pStyle")))
        np_ = ppr.find(q("numPr"))
        num_id = wval(np_.find(q("numId"))) if np_ is not None else None
        ilvl = wval(np_.find(q("ilvl"))) if np_ is not None else None
        ilvl = int(ilvl) if ilvl is not None else None
        s_num, s_ilvl = self._style_numpr(style)
        num_id = num_id if num_id is not None else s_num
        if num_id is None or num_id == "0" or num_id not in self.nums:
            return None
        aid = self._abstract_id(num_id)
        if ilvl is None:
            ilvl = s_ilvl
        if ilvl is None:   # a level may name the style it belongs to
            ilvl = next((i for i, lv in self.abstract.get(aid, {}).items() if style and lv.style == style), 0)

        c = self.counters.setdefault(aid, [None] * 9)
        if num_id not in self.seen_nums:          # first use of this w:num applies its overrides
            self.seen_nums.add(num_id)
            for il, s in self.nums[num_id][1].items():
                c[il] = s - 1
        lv = self._level(num_id, aid, ilvl)
        c[ilvl] = lv.start if c[ilvl] is None else c[ilvl] + 1
        for d in range(ilvl + 1, 9):
            r = self._level(num_id, aid, d).restart
            if r is None or (r != 0 and ilvl <= r - 1):
                c[d] = None
        self.used += 1

        if lv.fmt == "bullet":
            label = "•" if any(0xF000 <= ord(ch) <= 0xF0FF for ch in lv.text) else lv.text
        else:
            def sub(m):
                k = int(m.group(1)) - 1
                klv = self._level(num_id, aid, k)
                n = c[k] if c[k] is not None else klv.start
                return self._fmt(n, "decimal" if lv.legal and klv.fmt != "none" else klv.fmt)
            label = re.sub(r"%([1-9])", sub, lv.text)
        if not label:
            return ""
        return label + ("" if lv.suff == "nothing" else " ")


# ---------------- body walk ----------------

@dataclass
class Stats:
    revisions: int = 0
    hidden_runs: int = 0
    textboxes: int = 0
    notes: int = 0
    tables: int = 0


@dataclass
class Line:
    kind: str          # para | table_row
    text: str


@dataclass
class _Walk:
    numbering: Numbering
    stats: Stats = field(default_factory=Stats)


def _symbol(el) -> str:
    ch = el.get(q("char")) or ""
    try:
        cp = int(ch, 16)
    except ValueError:
        return ""
    if 0xF000 <= cp <= 0xF0FF:            # Symbol/Wingdings private-use range
        cp -= 0xF000
    return chr(cp) if cp >= 0x20 else ""


def _choice(alt):
    """mc:AlternateContent -> the first mc:Choice (mc:Fallback duplicates it)."""
    choice = alt.find(f"{{{MC}}}Choice")
    return choice if choice is not None else alt.find(f"{{{MC}}}Fallback")


def _run_text(r, w: _Walk, boxes: list) -> str:
    rpr = r.find(q("rPr"))
    if rpr is not None and _on(rpr.find(q("vanish"))):
        w.stats.hidden_runs += 1
        return ""
    out = []
    for c in r:
        t = local(c)
        if t == "t":
            out.append(c.text or "")
        elif t in ("tab", "ptab"):
            out.append("\t")
        elif t in ("br", "cr"):
            out.append("\n")
        elif t == "noBreakHyphen":
            out.append("-")
        elif t == "sym":
            out.append(_symbol(c))
        elif t in ("footnoteReference", "endnoteReference"):
            w.stats.notes += 1
        elif t in ("drawing", "pict", "object"):
            boxes.extend(c.iter(q("txbxContent")))
        elif t == "AlternateContent":
            if (ch := _choice(c)) is not None:
                boxes.extend(ch.iter(q("txbxContent")))
    return "".join(out)


_INLINE_WRAPPERS = {"hyperlink", "smartTag", "customXml", "fldSimple", "sdt", "sdtContent",
                    "dir", "bdo", "ins", "moveTo"}


def _inline(el, w: _Walk, boxes: list) -> str:
    out = []
    for c in el:
        t = local(c)
        if t == "r":
            out.append(_run_text(c, w, boxes))
        elif t in ("del", "moveFrom"):
            w.stats.revisions += 1
        elif t in _INLINE_WRAPPERS:
            if t in ("ins", "moveTo"):
                w.stats.revisions += 1
            out.append(_inline(c, w, boxes))
        elif t == "AlternateContent":
            if (ch := _choice(c)) is not None:
                out.append(_inline(ch, w, boxes))
    return "".join(out)


def _paragraph(p, w: _Walk, out: list[Line]) -> None:
    boxes: list = []
    text = _inline(p, w, boxes)
    label = w.numbering.label(p.find(q("pPr")))
    if label:
        text = label + text
    if text.strip():
        out.append(Line("para", text))
    for box in boxes:
        w.stats.textboxes += 1
        _container(box, w, out)


def _rows(tbl):
    for c in tbl:
        t = local(c)
        if t == "tr":
            yield c
        elif t in ("sdt", "sdtContent", "customXml"):
            yield from _rows(c)


def _cells(tr):
    for c in tr:
        t = local(c)
        if t == "tc":
            yield c
        elif t in ("sdt", "sdtContent", "customXml"):
            yield from _cells(c)


def _table(tbl, w: _Walk, out: list[Line]) -> None:
    w.stats.tables += 1
    for tr in _rows(tbl):
        cells = []
        for tc in _cells(tr):
            inner: list[Line] = []
            _container(tc, w, inner)
            cell = " ".join(" ".join(l.text.split()) for l in inner)
            if cell:
                cells.append(cell)
        if cells:
            out.append(Line("table_row", " | ".join(cells)))


def _container(el, w: _Walk, out: list[Line]) -> None:
    for c in el:
        t = local(c)
        if t == "p":
            _paragraph(c, w, out)
        elif t == "tbl":
            _table(c, w, out)
        elif t in ("sdt", "sdtContent", "customXml", "ins", "moveTo", "txbxContent"):
            _container(c, w, out)
        elif t in ("del", "moveFrom"):
            w.stats.revisions += 1
        elif t == "AlternateContent":
            if (ch := _choice(c)) is not None:
                _container(ch, w, out)


def extract(data: bytes) -> tuple[list[Line], list[str], dict]:
    """docx bytes -> (lines, warnings, raw info). Lines are not yet clean()ed."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = set(z.namelist())
        doc_xml = z.read("word/document.xml")
        numbering_xml = z.read("word/numbering.xml") if "word/numbering.xml" in names else None
        styles_xml = z.read("word/styles.xml") if "word/styles.xml" in names else None
    body = ET.fromstring(doc_xml).find(q("body"))
    w = _Walk(Numbering(numbering_xml, styles_xml))
    lines: list[Line] = []
    if body is not None:
        _container(body, w, lines)

    s, n = w.stats, w.numbering
    warnings = []
    if s.revisions:
        warnings.append(f"document has {s.revisions} tracked changes; text shows them accepted "
                        f"(insertions kept, deletions dropped)")
    if s.hidden_runs:
        warnings.append(f"{s.hidden_runs} hidden text runs were dropped")
    if s.textboxes:
        warnings.append(f"{s.textboxes} text boxes; their text is placed after the paragraph that anchors them")
    if s.notes:
        warnings.append(f"{s.notes} footnote/endnote references; note text is not included")
    if n.unknown_formats:
        warnings.append(f"unsupported list number formats rendered as decimal: {sorted(n.unknown_formats)}")
    raw = {"numbered_paragraphs": n.used, "tables": s.tables, "revisions": s.revisions,
           "has_numbering_xml": numbering_xml is not None}
    return lines, warnings, raw
