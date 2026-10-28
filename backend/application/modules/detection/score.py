"""Score grounded findings against a gold file (tools/plant_risks.py format).

present: a prediction matches a gold finding when their character spans have Jaccard >= 0.5 (CUAD's threshold);
         "loose" also counts any overlap. Each gold finding and each prediction is matched at most once.
decoys:  a prediction overlapping a decoy span is a false alarm on a lawful clause.
missing: there is no span to compare; until the checklist exists, missing predictions are listed next to the
         missing gold for a human (or judge) to pair.
Anything else the detector reported is "extra": a false positive if the gold is exhaustive, but worth reading.
"""
from __future__ import annotations

from application.modules.detection.finding import Finding

JACCARD = 0.5


def jaccard(a: tuple[int, int], b: tuple[int, int]) -> float:
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return inter / union if union else 0.0


def _match(golds: list[dict], preds: list[Finding], ok) -> dict[str, int]:
    """Greedy one-to-one matching by Jaccard; gold id -> index into preds."""
    pairs = sorted(((jaccard((g["char_start"], g["char_end"]), (p.char_start, p.char_end)), g["id"], i)
                    for g in golds for i, p in enumerate(preds)), reverse=True)
    out, used = {}, set()
    for j, gid, i in pairs:
        if ok(j) and gid not in out and i not in used:
            out[gid] = i
            used.add(i)
    return out


def score(gold: dict, preds: list[Finding]) -> dict:
    present_gold = [g for g in gold["findings"] if g["kind"] == "present"]
    present_pred = [p for p in preds if p.kind == "present"]
    strict = _match(present_gold, present_pred, lambda j: j >= JACCARD)
    loose = _match(present_gold, present_pred, lambda j: j > 0)
    decoy_hits = sorted({d["id"] for d in gold["decoys"] for p in present_pred
                         if jaccard((d["char_start"], d["char_end"]), (p.char_start, p.char_end)) > 0})
    matched = set(loose.values())
    extra = [p for i, p in enumerate(present_pred) if i not in matched
             and not any(jaccard((d["char_start"], d["char_end"]), (p.char_start, p.char_end)) > 0 for d in gold["decoys"])]

    def recall(m, origin):
        ids = [g["id"] for g in present_gold if origin in (None, g["origin"])]
        return sum(i in m for i in ids), len(ids)

    return {
        "strict": {o or "all": recall(strict, o) for o in ("planted", "natural", None)},
        "loose": {o or "all": recall(loose, o) for o in ("planted", "natural", None)},
        "found": {g["id"]: ("strict" if g["id"] in strict else "loose" if g["id"] in loose else "-") for g in present_gold},
        "decoy_hits": decoy_hits,
        "extra": extra,
        "missing_gold": [g for g in gold["findings"] if g["kind"] == "missing"],
        "missing_pred": [p for p in preds if p.kind == "missing"],
        "n_pred": len(preds),
    }
