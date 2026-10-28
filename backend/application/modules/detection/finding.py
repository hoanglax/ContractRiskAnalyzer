"""What detection produces, what it is asked to look for, and the gate between the two.

Detection is kept independent of the risk taxonomy and of any one detection method:
  LookFor  one thing to look for, from any source (a taxonomy row, a template clause, a checklist). A detector
           reads its text; it never depends on the source's codes, so the taxonomy can be renumbered or replaced.
  Finding  what a detector reports: a problem grounded in the contract (a verbatim quote, located and mapped to its
           clause by ground()), or a term the contract lacks. No taxonomy code and no severity: mapping a finding
           onto a taxonomy is a separate step that can be re-run when the taxonomy changes, and severity varied
           from run to run in the 2026-10-16 ReAct experiment while the flagged clauses did not.
  ground() the deterministic gate: a "present" finding whose quote is not in the contract is rejected, whatever the
           detector. Offsets and clause are set here, never taken from the model.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from application.modules.ingestion.ingest import Document
from application.modules.ingestion.text import find_span

KINDS = ("present", "missing")    # present: the quoted text is the problem; missing: the contract lacks a term
ROLES = ("lessor", "lessee", "both")
MIN_PART = 8                      # shortest piece of an elided quote ("A ... B") that may anchor a match
_ELISION = re.compile(r"\s*(?:\.{3,}|…)\s*")


@dataclass
class LookFor:
    id: str                    # unique across the list; "taxonomy:B-DEP-04", "nd96:Điều 5"
    title: str
    signs: str = ""            # how it shows up in a contract
    affects: str | None = None  # lessor | lessee | both | None
    meta: dict = field(default_factory=dict)   # source-specific (severity, citations ...); detectors pass it through


@dataclass
class Finding:
    kind: str                  # present | missing
    issue: str                 # what is wrong, in plain words
    quote: str | None = None   # verbatim from the contract (present only), as the detector gave it
    affects: str | None = None  # lessor | lessee | both | None (unknown)
    lens: list[str] = field(default_factory=list)   # LookFor ids that prompted it, if any
    detector: str = ""         # method + model, for comparing runs
    extra: dict = field(default_factory=dict)       # detector's own opinions (severity, legal basis ...), untrusted
    # set by ground()
    char_start: int | None = None
    char_end: int | None = None
    clause: str | None = None  # label of the level-1 clause the quote starts in, e.g. "Điều 5"; None = preamble etc.
    elided: bool = False       # the quote skipped text with "..." and was matched piece by piece


def locate(text: str, quote: str) -> tuple[int, int, bool] | None:
    """Offsets of `quote` in clean `text` as (start, end, elided), or None.

    The whole quote is tried first: contracts are full of "......" blanks, so "..." inside a quote is usually
    the contract's own. Only if that fails is the quote read as pieces joined by an elision, each found in order
    after the previous one; the span runs from the first piece to the last."""
    hit = find_span(text, quote)
    if hit:
        return hit[0], hit[1], False
    parts = [p for p in _ELISION.split(quote) if p.strip()]
    if len(parts) < 2 or any(len(p.strip()) < MIN_PART for p in parts):
        return None
    first = find_span(text, parts[0])
    if first is None:
        return None
    end = first[1]
    for p in parts[1:]:
        nxt = find_span(text, p, start=end)
        if nxt is None:
            return None
        end = nxt[1]
    return first[0], end, True


def clause_at(doc: Document, pos: int) -> str | None:
    for c in doc.structure.clauses:
        if c.char_start <= pos < c.char_end:
            return c.label
    return None


def ground(findings: list[Finding], doc: Document) -> tuple[list[Finding], list[tuple[Finding, str]]]:
    """Split findings into (kept, rejected with a reason). Kept present findings get offsets and a clause."""
    kept, rejected = [], []
    for f in findings:
        why = None
        if f.kind not in KINDS:
            why = f"unknown kind {f.kind!r}"
        elif not f.issue.strip():
            why = "no issue given"
        elif f.affects is not None and f.affects not in ROLES:
            why = f"unknown party {f.affects!r}"
        elif f.kind == "present":
            hit = locate(doc.text, f.quote or "") if (f.quote or "").strip() else None
            if hit is None:
                why = "quote not found verbatim in the contract" if (f.quote or "").strip() else "no quote"
            else:
                f.char_start, f.char_end, f.elided = hit
                f.clause = clause_at(doc, f.char_start)
        if why:
            rejected.append((f, why))
        else:
            kept.append(f)
    return kept, rejected
