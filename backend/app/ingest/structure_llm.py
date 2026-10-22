"""Clause map, tier 2: LLM fallback. Only called when tier 1 (app/ingest/structure.py) is not confident.

    segment_auto(text) -> (Structure, Diagnostics, warnings)

The model sees the document as numbered lines and answers with LINE NUMBERS only, so every heading it returns is a
verbatim line of `text` by construction; it never produces or changes text. Its answer is checked (lines exist,
increase, enough headings) and discarded with a warning if it fails. If the model is unreachable the tier-1 result is
returned with a warning. Results are cached by text hash + prompt version + model, so re-ingesting costs nothing.
Which model runs is decided by backend/llm.toml (task "structure_fallback")."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Callable

from app import llm
from app.ingest.ingest import Clause, Structure
from app.ingest.structure import Diagnostics, candidates, segment

TASK = "structure_fallback"
PROMPT_VERSION = "1"
CACHE = Path(__file__).resolve().parents[2] / "cache" / "structure"
LINE_CAP = 160                      # characters of each line shown to the model
MIN_HEADINGS = 2

PROMPT = """Below is a Vietnamese contract, one line per row as `<n>| <text>`.
List the line numbers of the headings that start each clause of the contract's terms (level 1 only).

A heading is a line that starts a clause: numbered (ĐIỀU 1, Điều I, I., 1.) or only titled (for example
TRÁCH NHIỆM CHUNG, a short standalone title in capitals or title case with no numbering).
NOT headings: the document title (HỢP ĐỒNG ...), the national motto, the legal-basis preamble (Căn cứ ...), party blocks
(BÊN A / BÊN B and their details), the signature block, ordinary list items (-, *, a)), and sentences that merely mention an article.
If the title sits on the line after a standalone marker (ĐIỀU 1 / then the title), give both line numbers in one entry.
If the contract has no clause headings at all, return an empty list.

Answer with JSON only: {"headings": [{"lines": [n]}, {"lines": [n, n+1]}]}

"""


def _numbered(text: str) -> tuple[list[str], str]:
    lines = text.split("\n")
    return lines, "\n".join(f"{i}| {ln[:LINE_CAP]}" for i, ln in enumerate(lines) if ln.strip())


def parse_answer(raw: str, lines: list[str]) -> list[tuple[int, int | None]] | str:
    """-> [(heading line, optional title line)] or an error string. Strict: anything odd is rejected."""
    hs = None
    for pat in (r"\{.*\}", r"\[.*\]"):                     # {"headings": [...]} first; a bare list ("[]" = none) also counts
        m = re.search(pat, raw, re.S)
        if not m:
            continue
        try:
            v = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        hs = v.get("headings") if isinstance(v, dict) else v
        if isinstance(hs, list):
            break
        hs = None
    if hs is None:
        return "no usable JSON in the model's answer"
    try:
        out = []
        for h in hs:
            ls = h["lines"]
            if not (isinstance(ls, list) and 1 <= len(ls) <= 2 and all(isinstance(x, int) for x in ls)):
                return "malformed heading entry"
            if any(not 0 <= x < len(lines) or not lines[x].strip() for x in ls):
                return "line number out of range or blank"
            if len(ls) == 2 and ls[1] != ls[0] + 1:
                return "two-line heading must be consecutive"
            out.append((ls[0], ls[1] if len(ls) == 2 else None))
    except (json.JSONDecodeError, KeyError, TypeError):
        return "unparseable answer"
    if any(b[0] <= a[0] for a, b in zip(out, out[1:])):
        return "heading lines not strictly increasing"
    return out


def _layout(lines_idx: list[int], text: str) -> str:
    _, _, fams, _ = candidates(text)
    names = {"dieu": "dieu_N", "dieu_r": "dieu_roman", "roman": "roman", "num": "numbered"}
    chosen = set(lines_idx)
    for fam, name in names.items():
        if len(chosen & {c.line for c in fams[fam]}) >= 0.8 * len(chosen):
            return name
    return "titled"


def build(text: str, picks: list[tuple[int, int | None]]) -> Structure:
    lines = text.split("\n")
    starts, pos = [], 0
    for ln in lines:
        starts.append(pos)
        pos += len(ln) + 1
    clauses = []
    for k, (a, t) in enumerate(picks):
        heading = lines[a] if t is None else f"{lines[a]} {lines[t]}"
        end = starts[picks[k + 1][0]] if k + 1 < len(picks) else len(text)
        clauses.append(Clause(label=lines[a][:60], heading=heading[:160], char_start=starts[a], char_end=end))
    return Structure(layout=_layout([a for a, _ in picks], text), clauses=clauses)


def _cache_key(text: str, model: str) -> Path:
    return CACHE / (hashlib.sha256(f"{PROMPT_VERSION}\0{model}\0{text}".encode()).hexdigest()[:32] + ".json")


def segment_llm(text: str, ask: Callable[..., llm.LLMResult] | None = None, use_cache: bool = True):
    """-> (Structure | None, warnings). None means 'no usable answer'; the caller keeps tier 1's result."""
    ask = ask or llm.chat
    lines, body = _numbered(text)
    try:
        profile, prof = llm.profile_for(TASK)
        key = _cache_key(text, f"{profile}:{prof.get('model')}")
    except llm.LLMError as e:
        return None, [f"structure fallback unavailable: {e}"]
    if use_cache and key.exists():
        picks = [tuple(p) for p in json.loads(key.read_text(encoding="utf-8"))["picks"]]
        return build(text, picks), [f"structure: tier-2 result from cache ({profile})"]
    try:
        r = ask(TASK, [{"role": "user", "content": PROMPT + body}])
    except llm.LLMError as e:
        return None, [f"structure fallback unavailable: {e}"]
    picks = parse_answer(r.text, lines)
    if isinstance(picks, str):
        return None, [f"structure fallback answer rejected ({picks})"]
    if r.finish_reason not in (None, "stop"):
        return None, [f"structure fallback answer rejected (finish_reason={r.finish_reason})"]
    if len(picks) < MIN_HEADINGS:
        return None, [f"structure fallback found {len(picks)} heading(s); treating the document as having no clause map"]
    if use_cache:
        CACHE.mkdir(parents=True, exist_ok=True)
        key.write_text(json.dumps({"picks": picks, "profile": profile, "model": r.model}), encoding="utf-8")
    return build(text, picks), [f"structure: tier-2 ({r.profile}) found {len(picks)} headings"]


def segment_auto(text: str, ask=None, use_cache: bool = True) -> tuple[Structure, Diagnostics, list[str]]:
    st, dg = segment(text)
    if not dg.needs_fallback:
        return st, dg, []
    st2, warns = segment_llm(text, ask, use_cache)
    if st2 is None:
        return st, dg, warns + [f"structure: tier-1 not confident ({', '.join(dg.reasons)})"]
    dg2 = Diagnostics(layout=st2.layout, n_lines=dg.n_lines, n_candidates=len(st2.clauses), n_headings=len(st2.clauses),
                      needs_fallback=False, reasons=["tier2"] + dg.reasons)
    return st2, dg2, warns
