"""Plant known risks into a contract template, for the detection eval set.

    cd backend && .venv/bin/python tools/plant_risks.py SPEC.json [--out-dir DIR]

A spec names a base contract and a list of edits on its Document.text (exact, unique old -> new strings). Each
edit is a planted risk, a decoy (a clause that sounds risky but is lawful: a detector must not flag it) or plain
scaffolding (e.g. renumbering after a deletion). The tool applies the edits, writes the planted contract as clean
text, and writes the gold: every planted finding and decoy with its span in the planted text, plus the natural
findings of the base that the spec lists (findings the template already had; these need a human check).

Spec:
  {"base": "templates/24_hop-dong.txt", "variant": "p1", "split": "dev", "exhaustive": true,
   "edits": [{"id": "P1", "role": "risk" | "decoy" | "scaffold", "old": "...", "new": "...",
              "finding": {"kind": "present" | "missing", "quote": "...", "issue": "...", "affects": "lessee",
                          "subtlety": "blatant" | "subtle", "basis": "...",
                          "codes": ["B-DEP-02", ...]},                              # finding: risk only
              "quote": "...", "why_fair": "..."}],                                   # decoy only
   "natural": [{"id": "N1", "kind": ..., "quote": ..., "issue": ..., "affects": ..., "confidence": "clear" | "debatable",
               "codes": [...]}]}
For a risk, the quote must be (part of) the edit's new text; a "missing" risk deletes text and has no quote.
"codes" are the taxonomy codes a correct finding may carry ([] if no row fits; see detection/evalset.py).
Paths in the spec are relative to data/test/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["STRUCTURE_LLM"] = "off"

from application.modules.detection.evalset import taxonomy_codes, validate  # noqa: E402
from application.modules.detection.finding import locate  # noqa: E402
from application.modules.ingestion.ingest import ingest  # noqa: E402
from application.modules.ingestion.text import clean  # noqa: E402

DATA = Path(__file__).resolve().parents[2] / "data" / "test"


def apply(spec: dict) -> tuple[str, dict]:
    base = ingest(DATA / spec["base"])
    text = base.text
    for e in spec["edits"]:
        n = text.count(e["old"])
        if n != 1:
            raise SystemExit(f"{e['id']}: 'old' occurs {n} times in the text so far, must be once: {e['old'][:60]!r}")
        text = text.replace(e["old"], e["new"])
    text = clean(text)
    doc = ingest(text.encode(), "planted.txt")
    if doc.text != text:
        raise SystemExit("planted text is not stable under ingest")

    def span(item, where):
        f = item.get("finding", item)
        if f.get("kind") == "missing":
            return {**f, "char_start": None, "char_end": None, "clause": None}
        hit = locate(doc.text, f["quote"])
        if hit is None or hit[2]:
            raise SystemExit(f"{item['id']} ({where}): quote not found verbatim in the planted text: {f['quote'][:60]!r}")
        clause = next((c.label for c in doc.structure.clauses if c.char_start <= hit[0] < c.char_end), None)
        return {**f, "quote": doc.text[hit[0]:hit[1]], "char_start": hit[0], "char_end": hit[1], "clause": clause}

    gold = {"contract": f"{Path(spec['base']).stem}_{spec['variant']}.txt", "source": spec["base"],
            "variant": spec["variant"], "split": spec.get("split", "dev"), "exhaustive": spec.get("exhaustive", True),
            "text_sha256": hashlib.sha256(doc.text.encode()).hexdigest(),
            "findings": [], "decoys": [], "edits": spec["edits"]}
    for e in spec["edits"]:
        if e["role"] == "risk":
            if e["finding"]["kind"] == "present" and e["finding"]["quote"] not in e["new"]:
                raise SystemExit(f"{e['id']}: the quote must come from the planted text of this edit")
            gold["findings"].append({"id": e["id"], "origin": "planted", **span(e, "risk")})
        elif e["role"] == "decoy":
            if e["quote"] not in e["new"]:
                raise SystemExit(f"{e['id']}: the quote must come from the planted text of this edit")
            gold["decoys"].append({"id": e["id"], **span({"id": e["id"], "quote": e["quote"], "kind": "present",
                                                          "why_fair": e["why_fair"]}, "decoy")})
    for n in spec.get("natural", []):
        gold["findings"].append({"id": n["id"], "origin": "natural", **span(n, "natural")})
    return doc.text, gold


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", type=Path)
    ap.add_argument("--out-dir", type=Path, default=DATA / "eval" / "planted")
    a = ap.parse_args()
    spec = json.loads(a.spec.read_text(encoding="utf-8"))
    text, gold = apply(spec)
    errs = validate(gold, text, taxonomy_codes())
    if errs:
        raise SystemExit("gold does not validate: " + "; ".join(errs))
    a.out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(gold["contract"]).stem
    (a.out_dir / gold["contract"]).write_text(text + "\n", encoding="utf-8")
    (a.out_dir / f"{stem}.gold.json").write_text(json.dumps(gold, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    kinds = [(f["origin"], f["kind"]) for f in gold["findings"]]
    print(f"{stem}: {len(gold['findings'])} findings "
          f"({kinds.count(('planted', 'present'))} planted present, {kinds.count(('planted', 'missing'))} planted missing, "
          f"{sum(o == 'natural' for o, _ in kinds)} natural), {len(gold['decoys'])} decoys -> {a.out_dir}")
    for f in gold["findings"] + gold["decoys"]:
        where = f"{f['clause'] or '-'} [{f['char_start']}:{f['char_end']}]" if f.get("char_start") is not None else "(missing)"
        print(f"  {f['id']:3} {where:22} {f.get('issue') or f.get('why_fair')}")


if __name__ == "__main__":
    main()
