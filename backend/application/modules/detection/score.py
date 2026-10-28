"""Score grounded findings against a gold file (tools/plant_risks.py format).

present: a prediction matches a gold finding when their character spans have Jaccard >= 0.5 (CUAD's threshold);
         "loose" also counts any overlap. Each gold finding and each prediction is matched at most once.
         A matched pair also has the right code when the prediction's code is one of the gold's "codes"; that
         recall is over gold that has codes (gold no taxonomy row fits is listed as "uncoded"). A detector often
         reports one clause under several codes (an A- and a B- row, or neighbouring rows), so among predictions
         that overlap enough, one with a right code is matched first; the others on a matched gold span are
         "dup": the same finding again, not a false positive.
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
    """Greedy one-to-one matching, right code first, then by Jaccard; gold id -> index into preds."""
    pairs = sorted(((p.code in g.get("codes", []), jaccard((g["char_start"], g["char_end"]), (p.char_start, p.char_end)),
                     g["id"], i) for g in golds for i, p in enumerate(preds)), reverse=True)
    out, used = {}, set()
    for _, j, gid, i in pairs:
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
    matched_spans = [(g["char_start"], g["char_end"]) for g in present_gold if g["id"] in loose]

    def overlaps(p, spans):
        return any(jaccard(sp, (p.char_start, p.char_end)) > 0 for sp in spans)

    decoy_spans = [(d["char_start"], d["char_end"]) for d in gold["decoys"]]
    rest = [p for i, p in enumerate(present_pred) if i not in matched and not overlaps(p, decoy_spans)]
    dup = [p for p in rest if overlaps(p, matched_spans)]
    extra = [p for p in rest if not overlaps(p, matched_spans)]

    by_id = {g["id"]: g for g in present_gold}
    code_ok = {gid: present_pred[i].code in by_id[gid]["codes"] for gid, i in loose.items()}

    def recall(m, origin, coded=False):
        ids = [g["id"] for g in present_gold if origin in (None, g["origin"]) and (g["codes"] or not coded)]
        return sum(i in m and (not coded or code_ok[i]) for i in ids), len(ids)

    return {
        "strict": {o or "all": recall(strict, o) for o in ("planted", "natural", None)},
        "loose": {o or "all": recall(loose, o) for o in ("planted", "natural", None)},
        "strict_code": {o or "all": recall(strict, o, True) for o in ("planted", "natural", None)},
        "loose_code": {o or "all": recall(loose, o, True) for o in ("planted", "natural", None)},
        "found": {g["id"]: ("strict" if g["id"] in strict else "loose" if g["id"] in loose else "-") for g in present_gold},
        "code_ok": code_ok,
        "code_of": {gid: present_pred[i].code for gid, i in loose.items()},
        "uncoded": [g["id"] for g in gold["findings"] if not g["codes"]],
        "decoy_hits": decoy_hits,
        "extra": extra,
        "dup": dup,
        "missing_gold": [g for g in gold["findings"] if g["kind"] == "missing"],
        "missing_pred": [p for p in preds if p.kind == "missing"],
        "n_pred": len(preds),
    }
