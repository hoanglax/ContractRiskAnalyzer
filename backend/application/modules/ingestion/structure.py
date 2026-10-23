"""Clause map, tier 1: deterministic. Finds the clause headings of a contract in its canonical text.

    segment(text) -> (Structure, Diagnostics)

`text` is Document.text (already clean()). Offsets are in that text. Tier 1 never rewrites text and never calls a
model; when it is not confident it says so (Diagnostics.needs_fallback) and a later tier decides.

Marker families, in priority order (a lower family is only used when a higher one yields nothing):
  dieu    "Điều 5." / "ĐIỀU 5:" / "Điều5" / standalone "ĐIỀU 5" (title on the next line)
  dieu_r  the same with a roman number: "ĐIỀU II:"
  roman   "I. Title"            needs a strictly increasing 1,2,3.. chain
  num     "1. Title"            ditto, plus a heading-shaped line (short, no trailing ; or ,)

Điều lines are accepted by shape (a sentence such as "Điều 6 của hợp đồng này" is rejected); their numbering is
only used for confidence, because real documents repeat, skip and restart numbers. Roman / arabic list markers
are everywhere in contracts (party blocks, sub-items), so those families must form a numbering chain.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from application.modules.ingestion.ingest import Clause, Structure

_LETTER = r"(?![^\W\d_])"                      # next char must not be a letter ("Điều lệ" is not roman L)
_DIEU = re.compile(rf"^điều\s*(\d{{1,3}}|[ivxl]{{1,6}}\d?){_LETTER}\s*([.:;)\-–—])?\s*(.*)$", re.I)
_ROMAN = re.compile(rf"^([IVXL]{{1,6}})\s*([.:)/])\s*(\S.*)$")
_NUM = re.compile(r"^(\d{1,3})\s*([.)])\s*(\S.*)$")
_ROMAN_VAL = {"I": 1, "V": 5, "X": 10, "L": 50}
MAX_TITLE = 160                                 # a title line longer than this is a paragraph
MIN_CHAIN = {"dieu": 3, "dieu_r": 3, "roman": 3, "num": 4}


def _roman(s: str) -> int | None:
    s = s.upper().rstrip("0123456789")           # tolerate the "ĐIỀU I1" typo seen in a real file
    if not s or any(c not in _ROMAN_VAL for c in s):
        return None
    total = 0
    for c, nxt in zip(s, s[1:] + " "):
        v = _ROMAN_VAL[c]
        total += -v if nxt in _ROMAN_VAL and _ROMAN_VAL[nxt] > v else v
    return total if 0 < total < 100 else None


@dataclass
class Cand:
    line: int                  # index into text.split("\n")
    family: str
    number: int
    marker: str                # as written ("Điều 5", "II")
    rest: str                  # text after the marker on the same line
    char_start: int


@dataclass
class Diagnostics:
    layout: str = "none"       # dieu_N | dieu_roman | roman | numbered | none
    n_lines: int = 0
    n_candidates: int = 0      # shape-valid marker lines in the chosen family
    n_headings: int = 0
    numbers: list[int] = field(default_factory=list)
    dups: int = 0              # same number twice in a row
    gaps: int = 0              # jumps of 2 or 3
    resets: int = 0            # number goes down
    chars_before_first: float = 0.0   # share of the text before the first heading
    needs_fallback: bool = True
    reasons: list[str] = field(default_factory=list)


def candidates(text: str) -> tuple[list[str], list[int], dict[str, list[Cand]], list[tuple[int, str, int]]]:
    lines = text.split("\n")
    starts, pos = [], 0
    for ln in lines:
        starts.append(pos)
        pos += len(ln) + 1
    fams: dict[str, list[Cand]] = {"dieu": [], "dieu_r": [], "roman": [], "num": []}
    rejected: list[tuple[int, str, int]] = []
    for i, ln in enumerate(lines):
        if not ln:
            continue
        m = _DIEU.match(ln)
        if m:
            tok, delim, rest = m.group(1), m.group(2), m.group(3).strip()
            is_digit = tok[0].isdigit()
            n = int(tok) if is_digit else _roman(tok)
            # a delimiter after the marker is strong evidence, whatever the length ("Điều 3: Bên thuê phải trả ... .");
            # without one, only a standalone marker or a capitalised title counts
            if n is not None and not delim and rest and (not rest[0].isupper() or len(ln) > MAX_TITLE):
                rejected.append((i, "dieu" if is_digit else "dieu_r", n))     # "Điều 6 của hợp đồng này", "Điều 6, Điều 7 ..."
                continue
            if n is not None:
                marker = ln[: m.end(1)]                     # "Điều 5" / "ĐIỀU II" exactly as written, no delimiter
                fams["dieu" if is_digit else "dieu_r"].append(Cand(i, "dieu" if is_digit else "dieu_r", n, marker, rest, starts[i]))
            continue
        m = _ROMAN.match(ln)
        if m and _roman(m.group(1)):
            fams["roman"].append(Cand(i, "roman", _roman(m.group(1)), m.group(1), m.group(3).strip(), starts[i]))
            continue
        m = _NUM.match(ln)
        if m:
            rest = m.group(3).strip()
            if len(rest) <= 90 and rest[0].isupper() and rest[-1] not in ";,":
                fams["num"].append(Cand(i, "num", int(m.group(1)), m.group(1), rest, starts[i]))
    return lines, starts, fams, rejected


def best_chain(cs: list[Cand]) -> list[Cand]:
    """Longest numbering chain 1,2,3.. (a repeat or a skip of 1-2 is allowed at a small cost)."""
    if not cs:
        return []
    score, prev = [], []
    for i, c in enumerate(cs):
        best, arg = (1.0 - 0.5 * (c.number - 1), -1) if c.number <= 2 else (float("-inf"), -1)
        for j in range(i):
            d = c.number - cs[j].number
            gain = {1: 1.0, 0: 0.5, 2: 0.5, 3: 0.0}.get(d)
            if gain is not None and score[j] + gain > best:
                best, arg = score[j] + gain, j
        score.append(best)
        prev.append(arg)
    end = max(range(len(cs)), key=lambda k: (score[k], k))
    if score[end] == float("-inf"):
        return []
    chain = []
    while end != -1:
        chain.append(cs[end])
        end = prev[end]
    return chain[::-1]


def segment(text: str) -> tuple[Structure, Diagnostics]:
    lines, starts, fams, rejected = candidates(text)
    diag = Diagnostics(n_lines=len(lines))
    chosen: list[Cand] = []
    layout = "none"
    # Điều families: shape-valid lines are headings; the bigger of arabic / roman wins
    dieu = max((fams["dieu"], fams["dieu_r"]), key=len)
    if len(dieu) >= MIN_CHAIN["dieu"]:
        chosen, layout = dieu, "dieu_N" if dieu is fams["dieu"] else "dieu_roman"
        diag.n_candidates = len(dieu)
    else:
        for fam, name in (("roman", "roman"), ("num", "numbered")):
            chain = best_chain(fams[fam])
            if len(chain) >= MIN_CHAIN[fam]:
                chosen, layout = chain, name
                diag.n_candidates = len(fams[fam])
                break
    diag.layout = layout
    if not chosen:
        diag.reasons.append("no_marker_chain")
        return Structure(layout="freeform", clauses=[]), diag

    clauses = []
    for k, c in enumerate(chosen):
        heading = c.marker
        if c.rest:
            heading = (f"{c.marker}. {c.rest}" if c.family.startswith("dieu") else f"{c.marker} {c.rest}")[:MAX_TITLE]
        elif c.line + 1 < len(lines) and lines[c.line + 1] and len(lines[c.line + 1]) <= MAX_TITLE \
                and not any(x.line == c.line + 1 for fam in fams.values() for x in fam):
            heading = f"{c.marker} {lines[c.line + 1]}"        # standalone "ĐIỀU 1" + title on the next line
        end = chosen[k + 1].char_start if k + 1 < len(chosen) else len(text)
        label = f"Điều {c.marker.split()[-1]}" if c.family.startswith("dieu") else c.marker
        clauses.append(Clause(label=label, heading=heading, char_start=c.char_start, char_end=end))

    nums = [c.number for c in chosen]
    diag.numbers, diag.n_headings = nums, len(chosen)
    for a, b in zip(nums, nums[1:]):
        d = b - a
        diag.dups += d == 0
        diag.gaps += d in (2, 3)
        diag.resets += d < 0 or d > 3
    diag.chars_before_first = chosen[0].char_start / max(len(text), 1)

    if diag.n_candidates and (diag.n_candidates - diag.n_headings) / diag.n_candidates > 0.25 and diag.n_candidates - diag.n_headings >= 3:
        diag.reasons.append("many_unfit_candidates")
    # numbering quirks (repeats, skips, restarts) are normal in real files and prove nothing by themselves; a skipped number
    # only matters if a rejected Điều-shaped line carrying that number sits in the gap (a possibly missed heading)
    fam = chosen[0].family
    for a, b in zip(chosen, chosen[1:]):
        missing = set(range(a.number + 1, b.number)) if b.number > a.number + 1 else set()
        if any(a.line < ln < b.line and f == fam and n in missing for ln, f, n in rejected):
            diag.reasons.append("gap_filled_by_rejected_line")
            break
    if (diag.dups + diag.gaps + diag.resets) > 0.5 * diag.n_headings:
        diag.reasons.append("very_irregular_numbering")
    if nums[0] > 2:
        diag.reasons.append("does_not_start_at_1")
    if diag.chars_before_first > 0.5:
        diag.reasons.append("headings_start_late")
    diag.needs_fallback = bool(diag.reasons)
    return Structure(layout=layout, clauses=clauses), diag
