"""Demo of the tier-1 segmenter: application.modules.ingestion.structure.segment(text) -> (Structure, Diagnostics).

    cd backend && .venv/bin/python tools/demo_segment.py [files...] [--max-clauses 12]

With no arguments it demos data/test/text.txt. Also good examples:
    python tools/demo_segment.py ../data/legal_corpus/nd125_2020.txt

Input goes through clean() first, exactly like Document.text, so offsets printed here are the offsets
ingest would hand to the gate. Tier 1 only: deterministic, no model call.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from application.modules.ingestion.structure import segment
from application.modules.ingestion.text import clean


def preview(s: str, n: int = 70) -> str:
    s = " ".join(s.split())
    return (s[: n - 1] + "…") if len(s) > n else s


def show(path: pathlib.Path, max_clauses: int) -> None:
    raw = path.read_text(encoding="utf-8", errors="replace")
    text = clean(raw)                      # same canonical form ingest stores as Document.text
    structure, diag = segment(text)

    print(f"\n=== {path} ===")
    print(f"clean text: {len(text)} chars, {diag.n_lines} lines")
    print(f"layout: {structure.layout}   needs_fallback: {diag.needs_fallback}")
    print(f"candidates: {diag.n_candidates}   headings: {diag.n_headings}   "
          f"dups: {diag.dups}  gaps: {diag.gaps}  resets: {diag.resets}   "
          f"before_first: {diag.chars_before_first:.1%}")
    if diag.numbers:
        print(f"numbers: {diag.numbers}")
    if diag.reasons:
        print(f"reasons: {', '.join(diag.reasons)}")

    shown = structure.clauses[:max_clauses]
    print(f"\nclauses ({len(structure.clauses)} found"
          + (f", showing first {max_clauses}" if len(structure.clauses) > max_clauses else "") + "):")
    for c in shown:
        body = text[c.char_start:c.char_end]
        print(f"  {c.label:<10} [{c.char_start:>6}:{c.char_end:>6}]  {preview(c.heading, 60)}")
        print(f"  {'':<10} body {len(body)} chars | {preview(body, 90)}")
    if len(structure.clauses) > max_clauses:
        last = structure.clauses[-1]
        print(f"  ... last: {last.label} [{last.char_start}:{last.char_end}]")


def main() -> int:
    ap = argparse.ArgumentParser(description="Demo of the tier-1 clause segmenter (structure.segment).")
    ap.add_argument("files", nargs="*", type=pathlib.Path)
    ap.add_argument("--max-clauses", type=int, default=12)
    args = ap.parse_args()
    files = args.files or [pathlib.Path(__file__).resolve().parent.parent.parent / "data/test/text.txt"]
    for p in files:
        show(p, args.max_clauses)
    return 0


if __name__ == "__main__":
    sys.exit(main())
