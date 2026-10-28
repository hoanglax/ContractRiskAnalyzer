"""Draft a 2-level heading tree for contracts with an LLM, as prefill for tools/label_headings.py.

    cd backend && .venv/bin/python tools/llm_label_tree.py FILE... --out PATH

The model sees Document.text (ingest, tier 1 only) as numbered lines and answers with line numbers only, so every label
is a line of the text verbatim (the method of the 2026-10-13 relabel, extended to 2 levels). Units are split on
their numbering, not on whether the line reads like a title: "2.1 Thời hạn thuê:" and "2.1 Bên A giao nhà ..." are both
level 2. Anything below level 2 (a), b), 2.1.1, bullets) stays inside its level-2 unit. Output rows: {"source", "text_sha256", "layout", "headings": [{"line", "level"}], "description", "confidence",
"finish", "usage"}; a title on the line after a standalone marker ("ĐIỀU 1" / "TÊN ĐIỀU") is listed with the same level,
matching the hand labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["STRUCTURE_LLM"] = "off"

from application.modules.ingestion.ingest import ingest  # noqa: E402
from application.adapters.llm import chat  # noqa: E402

LAYOUTS = ["dieu_N", "dieu_roman", "roman", "numbered", "titled", "freeform"]

PROMPT = """Below is a Vietnamese contract, one line per row as `<n>| <text>`.
List the units the contract's terms are divided into, in two levels. Report what is actually there; do not force a scheme.

- Level 1: a line that starts a clause of the terms. Numbered (ĐIỀU 1, Điều I, I., 1.) or an unnumbered section title written as a heading line (e.g. "TRÁCH NHIỆM CỦA CÁC BÊN", "TRÁCH NHIỆM CHUNG"): when a contract has no numbered clauses, its section titles are its level-1 units.
- Level 2: the first numbered subdivision inside a level-1 clause: 2.1, 2.2 ... or 1., 2. ... or a), b) / a/, b/ when that is the first level of numbering inside the clause.
Go no deeper: numbering below level 2 (2.1.1, or a), b) under a 2.1) and all unnumbered bullets (-, *, +, •) stay inside their level-2 unit and are not listed.
Split on the numbering, not on how the line reads: "2.1 Thời hạn thuê:" (a title) and "2.1 Bên A giao nhà cho Bên B ..." (a full sentence) are both level 2. A level-1 line can itself be the whole clause ("Điều 2: Tiền thuê nhà là ... đồng.").
NOT units: the document title (HỢP ĐỒNG ...), the national motto, the legal-basis preamble (Căn cứ ...), party blocks (BÊN A / BÊN B and their details), the signature block, and an appendix (Phụ lục) unless it has clauses of its own.
If a level-1 marker stands alone and the next line is its title (a short heading such as "ĐỐI TƯỢNG HỢP ĐỒNG"), give both line numbers. If the next line is the clause's content (a sentence such as "Tiền thuê nhà hàng tháng là ... đồng."), give only the marker line.

Answer with JSON only:
{"layout": "dieu_N | dieu_roman | roman | numbered | titled | freeform",
 "description": "one or two sentences on how the clauses and their subdivisions are marked, including any inconsistency",
 "units": [{"lines": [n] or [n, n+1], "level": 1 | 2}],
 "confidence": "high|medium|low"}
List units in document order. If there are none, use an empty list.

"""


def label(path: Path) -> dict:
    text = ingest(path).text
    lines = text.split("\n")
    body = "\n".join(f"{i}| {l[:160]}" for i, l in enumerate(lines) if l.strip())
    r = chat("structure_fallback", [{"role": "user", "content": PROMPT + body}], sampling={"max_tokens": 12000})
    row = {"source": path.name, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
           "finish": r.finish_reason, "usage": r.usage}
    try:
        ans = json.loads(re.search(r"\{.*\}", r.text, re.S).group(0))
    except (AttributeError, json.JSONDecodeError) as e:
        return {**row, "error": repr(e), "raw": r.text, "layout": "freeform", "headings": []}
    heads, seen = [], set()
    for u in ans.get("units", []):
        lv = u.get("level")
        for n in u.get("lines", []):
            if isinstance(n, int) and 0 <= n < len(lines) and lines[n].strip() and lv in (1, 2) and n not in seen:
                heads.append({"line": n, "level": lv})
                seen.add(n)
    layout = ans.get("layout")
    return {**row, "layout": layout if layout in LAYOUTS else "freeform", "headings": sorted(heads, key=lambda h: h["line"]),
            "description": ans.get("description"), "confidence": ans.get("confidence")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    with a.out.open("a", encoding="utf-8") as f:
        for p in a.files:
            t = time.time()
            row = label(p)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            lv = [sum(h["level"] == k for h in row["headings"]) for k in (1, 2)]
            print(f"{p.name}: {time.time() - t:.0f}s {row['finish']} L1/L2={lv} {row.get('error', '')}", flush=True)


if __name__ == "__main__":
    main()
