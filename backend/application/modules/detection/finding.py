"""What detection produces, what it is asked to look for, and the gate between the two.

  LookFor  one risk the detector may report, from a closed list (the taxonomy, via lens.py). A detector reads its
           text and echoes its id back as the finding's code; it never invents a code.
  Finding  what a detector reports: a risk from the list grounded in the contract (a verbatim quote, located and
           mapped to its clause by ground()), or a listed term the contract lacks. No severity from the model:
           severity, party and citations come from the list's row (severity varied from run to run in the
           2026-10-16 ReAct experiment while the flagged clauses did not).
  ground() the deterministic gate: a finding whose code is not on the list, or a "present" finding whose quote is
           not in the contract, is rejected, whatever the detector. Offsets, clause and party are set here, never
           taken from the model.
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
    id: str                    # unique across the list; the code findings carry, e.g. "B-DEP-04"
    title: str
    signs: str = ""            # how it shows up in a contract
    affects: str | None = None  # lessor | lessee | both | None
    meta: dict = field(default_factory=dict)   # source-specific (severity, citations ...); detectors pass it through


@dataclass
class Finding:
    kind: str                  # present | missing
    issue: str                 # what is wrong, in plain words
    code: str | None = None    # id of the LookFor it reports; must be on the list given to ground()
    quote: str | None = None   # verbatim from the contract (present only), as the detector gave it
    detector: str = ""         # method + model, for comparing runs
    extra: dict = field(default_factory=dict)       # detector's own opinions (severity, legal basis ...), untrusted
    # set by ground()
    affects: str | None = None  # lessor | lessee | both, from the LookFor
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


def ground(findings: list[Finding], doc: Document,
           allowed: list[LookFor]) -> tuple[list[Finding], list[tuple[Finding, str]]]:
    """Split findings into (kept, rejected with a reason). `allowed` is the closed list: a code outside it is
    rejected first. Kept findings get their party from the LookFor; kept present findings get offsets and a clause."""
    by_id = {l.id: l for l in allowed}
    kept, rejected = [], []
    for f in findings:
        why = None
        if f.code not in by_id:
            why = f"unknown code {f.code!r}" if f.code else "no code"
        elif f.kind not in KINDS:
            why = f"unknown kind {f.kind!r}"
        elif not f.issue.strip():
            why = "no issue given"
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
            f.affects = by_id[f.code].affects
            kept.append(f)
    return kept, rejected
