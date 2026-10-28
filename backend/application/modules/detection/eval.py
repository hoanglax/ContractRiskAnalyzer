"""Run detector configs over the eval set, save every prediction, score and report.

    python -m application.modules.detection.eval run [--config whole_doc/none ...] [--runs 3] [--split dev]
    python -m application.modules.detection.eval rescore data/test/eval/runs/<stamp>       # after the gold changed; no model calls
    python -m application.modules.detection.eval list                                      # the eval set and the configs

A run writes data/test/eval/runs/<stamp>/: manifest.json (configs, git commit, LLM profile and the model the server
reports, prompt hashes, gold hashes) and one predictions file per config x contract x run. Scoring reads only those
files and the current gold, so relabelling never needs the model again. Predictions whose contract text changed are
skipped (their offsets no longer apply).
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime
import hashlib
import json
import statistics
import subprocess
import time
import urllib.request
from pathlib import Path

from application.adapters import llm
from application.modules.detection import evalset, whole_doc
from application.modules.detection.finding import Finding
from application.modules.detection.lens import from_taxonomy
from application.modules.detection.score import score
from application.modules.ingestion.ingest import ingest
from application.modules.taxonomy import taxonomy

REPO = Path(__file__).resolve().parents[4]
RUNS = evalset.EVAL_DIR / "runs"
LENSES = {"none": lambda: None, "taxonomy": lambda: from_taxonomy(taxonomy.load())}
DETECTORS = {"whole_doc": (whole_doc.detect, whole_doc.PROMPT)}     # name -> (fn(doc, lens) -> dict, prompt)


def configs() -> list[str]:
    return [f"{d}/{l}" for d in DETECTORS for l in LENSES]


def _git() -> dict:
    def g(*args):
        r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None
    return {"commit": g("rev-parse", "HEAD"), "dirty": bool(g("status", "--porcelain", "--", "backend"))}


def _server_model(task: str = "detect") -> dict:
    name, prof = llm.profile_for(task)
    info = {"profile": name, "base_url": prof["base_url"], "model": prof.get("model"),
            "sampling": prof.get("sampling", {})}
    try:
        with urllib.request.urlopen(prof["base_url"].rstrip("/") + "/models", timeout=5) as r:
            info["server_models"] = [m.get("id") for m in json.load(r).get("data", [])]
    except Exception as e:     # best effort: the manifest is still useful without it
        info["server_models"] = f"unavailable ({e})"
    return info


def run(cfgs: list[str], runs: int, split: str | None, temperature: float | None = None) -> Path:
    gold = evalset.load_all(split=split)
    if not gold:
        raise SystemExit(f"no gold contracts{f' in split {split!r}' if split else ''} under {evalset.EVAL_DIR}")
    out = RUNS / datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    (out / "manifest.json").write_text(json.dumps({
        "created": datetime.datetime.now().isoformat(timespec="seconds"), "configs": cfgs, "runs": runs,
        "split": split, "temperature": temperature, "git": _git(), "llm": _server_model(),
        "prompts": {d: hashlib.sha256(p.encode()).hexdigest()[:16] for d, (_, p) in DETECTORS.items()},
        "gold": {g.name: hashlib.sha256(g.path.read_bytes()).hexdigest()[:16] for g in gold},
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    for cfg in cfgs:
        det, lens_name = cfg.split("/")
        fn, lens = DETECTORS[det][0], LENSES[lens_name]()
        for g in gold:
            doc = ingest(g.text.encode(), g.gold["contract"])
            for r in range(1, runs + 1):
                t = time.time()
                res = fn(doc, lens, temperature=temperature)
                rec = {"config": cfg, "contract": g.name, "run": r, "seconds": round(time.time() - t, 1),
                       "text_sha256": g.gold["text_sha256"], "finish": res["finish"], "usage": res["usage"],
                       "error": res["error"], "kept": [dataclasses.asdict(f) for f in res["kept"]],
                       "rejected": [{**dataclasses.asdict(f), "why": w} for f, w in res["rejected"]], "raw": res["raw"]}
                (out / f"{cfg.replace('/', '__')}__{g.name}__r{r}.json").write_text(
                    json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"{cfg:22} {g.name:28} r{r}: {rec['seconds']:5.0f}s  {len(res['kept'])} kept, "
                      f"{len(res['rejected'])} rejected{'  ERROR ' + res['error'] if res['error'] else ''}", flush=True)
    return out


def rescore(run_dir: Path, split: str | None = None) -> dict:
    gold = {g.name: g for g in evalset.load_all(split=split)}
    results, skipped = {}, []
    for p in sorted(run_dir.glob("*__r*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        g = gold.get(rec["contract"])
        if g is None:
            continue
        if rec["text_sha256"] != g.gold["text_sha256"]:
            skipped.append(p.name)
            continue
        kept = [Finding(**f) for f in rec["kept"]]
        s = score(g.gold, kept) if not rec["error"] else None
        results.setdefault(rec["config"], []).append({"rec": rec, "score": s, "gold": g})
    if skipped:
        print(f"skipped {len(skipped)} predictions whose contract text changed: {skipped[:3]}")
    return results


def report(results: dict, run_dir: Path) -> None:
    lines = []
    for cfg, items in results.items():
        ok = [i for i in items if i["score"]]
        by_run = {}
        for i in ok:
            by_run.setdefault(i["rec"]["run"], []).append(i)

        def rec_rate(kind, origin):
            per = []
            for its in by_run.values():
                hit = sum(i["score"][kind][origin][0] for i in its)
                tot = sum(i["score"][kind][origin][1] for i in its)
                per.append(hit / tot if tot else None)
            per = [x for x in per if x is not None]
            if not per:
                return "   -   "
            return f"{statistics.mean(per):.2f}" + (f" ({min(per):.2f}-{max(per):.2f})" if len(per) > 1 else "")

        n_dec = sum(len(i["gold"].gold["decoys"]) for i in ok)
        dec_hit = sum(len(i["score"]["decoy_hits"]) for i in ok)
        exh = [i for i in ok if i["gold"].gold["exhaustive"]]
        n_pred = sum(len(i["rec"]["kept"]) + len(i["rec"]["rejected"]) for i in items)
        n_rej = sum(len(i["rec"]["rejected"]) for i in items)
        lines += [f"\n## {cfg}  ({len(by_run)} runs x {len({i['rec']['contract'] for i in items})} contracts, "
                  f"{sum(1 for i in items if i['rec']['error'])} unparseable replies)",
                  f"present recall  strict planted {rec_rate('strict', 'planted')}  natural {rec_rate('strict', 'natural')}"
                  f"  all {rec_rate('strict', 'all')}",
                  f"                loose  planted {rec_rate('loose', 'planted')}  natural {rec_rate('loose', 'natural')}"
                  f"  all {rec_rate('loose', 'all')}",
                  f"decoys flagged  {dec_hit}/{n_dec}" if n_dec else "decoys flagged  (no decoys)",
                  f"extra findings  {sum(len(i['score']['extra']) for i in exh) / max(len(exh), 1):.1f} per contract (exhaustive gold only)",
                  f"gate rejected   {n_rej}/{n_pred} predicted findings",
                  f"seconds         {statistics.mean(i['rec']['seconds'] for i in items):.0f} per contract"]
    print("\n".join(lines))
    # missing findings and extras need a human until the checklist and judge exist
    review = ["# For review: missing findings and extras\n"]
    for cfg, items in results.items():
        for i in items:
            if not i["score"]:
                continue
            s, name = i["score"], f"{cfg} {i['rec']['contract']} r{i['rec']['run']}"
            review.append(f"## {name}\nmissing gold:\n" + "".join(f"- {g['id']}: {g['issue']}\n" for g in s["missing_gold"])
                          + "missing predicted:\n" + "".join(f"- {f.issue}\n" for f in s["missing_pred"])
                          + "extra (not in gold):\n" + "".join(f"- [{f.clause}] «{f.quote}» {f.issue}\n" for f in s["extra"]))
    (run_dir / "review.md").write_text("\n".join(review), encoding="utf-8")
    (run_dir / "report.txt").write_text("\n".join(lines).lstrip() + "\n", encoding="utf-8")
    print(f"\nreport and review notes in {run_dir}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "rescore", "list"])
    ap.add_argument("run_dir", nargs="?", type=Path)
    ap.add_argument("--config", action="append", choices=configs())
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--split", choices=evalset.SPLITS)
    ap.add_argument("--temperature", type=float, help="default: the LLM profile's (0); repeated runs only differ above 0")
    a = ap.parse_args()
    if a.cmd == "list":
        for g in evalset.load_all():
            kinds = [(f["origin"], f["kind"]) for f in g.gold["findings"]]
            print(f"{g.name:30} {g.gold['split']:4} findings={len(kinds)} decoys={len(g.gold['decoys'])} "
                  f"exhaustive={g.gold['exhaustive']}")
        print("configs:", ", ".join(configs()))
        return
    if a.cmd == "run":
        run_dir = run(a.config or configs(), a.runs, a.split, a.temperature)
    else:
        if not a.run_dir:
            raise SystemExit("rescore needs a run directory")
        run_dir = a.run_dir
    report(rescore(run_dir, a.split), run_dir)


if __name__ == "__main__":
    main()
