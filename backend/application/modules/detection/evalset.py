"""The detection eval set: gold files, how to load them and what makes one valid.

One gold file per contract, `<name>.gold.json`, next to the contract text `<name>.txt` (clean text, = Document.text):
  {"contract": "<name>.txt", "source": "templates/24_hop-dong.txt", "variant": "p1" | null,
   "split": "dev" | "test", "exhaustive": true,          # true: anything not in findings or decoys is fine text
   "text_sha256": "<sha256 of the contract text>",
   "findings": [{"id", "origin": "planted" | "natural", "kind": "present" | "missing",
                 "quote", "char_start", "char_end", "clause",   # present only; null for missing
                 "issue", "affects": "lessor" | "lessee" | "both",
                 "codes": ["B-DEP-04", ...]}],                  # taxonomy codes that count as the right risk

   "decoys":   [{"id", "quote", "char_start", "char_end", "clause", "why_fair"}]}
"codes" lists every taxonomy code a correct finding may carry (a clause can fit more than one row, and a risk to
both parties has an A- and a B- code). An empty list means no row fits: detection, which only reports taxonomy codes,
cannot find it, and the gap is reported so the workbook can get a row. No severity: that comes from the row.
Extra keys are kept and ignored.
Gold is written by tools/plant_risks.py (planted contracts) or by hand-labelling (natural contracts).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from application.modules.detection.finding import KINDS, ROLES
from application.modules.taxonomy import taxonomy

EVAL_DIR = Path(__file__).resolve().parents[4] / "data" / "test" / "eval"
ORIGINS = ("planted", "natural")
SPLITS = ("dev", "test")


@dataclass
class GoldContract:
    path: Path                 # the .gold.json
    text: str                  # the contract text the spans index into
    gold: dict

    @property
    def name(self) -> str:
        return self.path.name.removesuffix(".gold.json")


def validate(gold: dict, text: str, codes: set[str] | None = None) -> list[str]:
    """Problems with a gold file against its contract text; [] if it is usable. `codes`: the taxonomy's codes,
    which every gold code must be one of (None skips that check)."""
    errs = []
    if gold.get("text_sha256") != hashlib.sha256(text.encode()).hexdigest():
        errs.append("text_sha256 does not match the contract text (the text changed after labelling)")
    if gold.get("split") not in SPLITS:
        errs.append(f"split must be one of {SPLITS}")
    if not isinstance(gold.get("exhaustive"), bool):
        errs.append("exhaustive must be true or false")
    ids = [x.get("id") for x in gold.get("findings", []) + gold.get("decoys", [])]
    if len(ids) != len(set(ids)) or None in ids:
        errs.append("finding/decoy ids must be present and unique")

    def check_span(x, label):
        s, e = x.get("char_start"), x.get("char_end")
        if not (isinstance(s, int) and isinstance(e, int) and 0 <= s < e <= len(text)):
            errs.append(f"{label}: bad span {s}:{e}")
        elif text[s:e] != x.get("quote"):
            errs.append(f"{label}: quote differs from the text at its span")

    for f in gold.get("findings", []):
        label = f"finding {f.get('id')}"
        if f.get("origin") not in ORIGINS:
            errs.append(f"{label}: origin must be one of {ORIGINS}")
        if f.get("kind") not in KINDS:
            errs.append(f"{label}: kind must be one of {KINDS}")
        if f.get("affects") not in ROLES:
            errs.append(f"{label}: affects must be one of {ROLES}")
        if not (f.get("issue") or "").strip():
            errs.append(f"{label}: no issue")
        fc = f.get("codes")
        if not (isinstance(fc, list) and all(isinstance(c, str) for c in fc)):
            errs.append(f"{label}: codes must be a list of taxonomy codes ([] if none fits)")
        elif codes is not None and set(fc) - codes:
            errs.append(f"{label}: codes not in the taxonomy: {sorted(set(fc) - codes)}")
        if f.get("kind") == "present":
            check_span(f, label)
        elif f.get("char_start") is not None or f.get("quote"):
            errs.append(f"{label}: a missing finding has no quote or span")
    for d in gold.get("decoys", []):
        check_span(d, f"decoy {d.get('id')}")
        if not (d.get("why_fair") or "").strip():
            errs.append(f"decoy {d.get('id')}: no why_fair")
    return errs


def taxonomy_codes() -> set[str]:
    return set(taxonomy.load().by_code)


def load(path: Path, codes: set[str] | None = None) -> GoldContract:
    gold = json.loads(path.read_text(encoding="utf-8"))
    text_path = path.parent / gold["contract"]
    text = text_path.read_text(encoding="utf-8").rstrip("\n")
    errs = validate(gold, text, codes)
    if errs:
        raise ValueError(f"{path.name}: " + "; ".join(errs))
    return GoldContract(path, text, gold)


def load_all(root: Path = EVAL_DIR, split: str | None = None) -> list[GoldContract]:
    codes = taxonomy_codes()
    out = [load(p, codes) for p in sorted(root.rglob("*.gold.json")) if "runs" not in p.relative_to(root).parts]
    return [g for g in out if split in (None, g.gold["split"])]
