"""Retrieval eval: recall@k and MRR on the gold article, by split / style / tier.

    python -m application.modules.legal_retrieval.eval [--split dev|test] [-k 5]

`abstain` rows have no gold (the question is about a law that was not in the KB when the set was
written); they are listed with their top hit instead of being scored.
Honest headline = --split test; tune on --split dev only.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

from application.modules.legal_retrieval.kb import DEFAULT_DB, REPO, LexicalRetriever

EVAL = REPO / "data" / "legal_eval" / "retrieval_v2.jsonl"


def rank_of(hits, gold) -> int | None:
    """1-based rank of the first gold article among the hits, deduplicated by article."""
    want = {(g["law"].removesuffix(".txt"), g["dieu"]) for g in gold}
    seen = []
    for h in hits:
        key = (h.law, h.dieu_no)
        if key not in seen:
            seen.append(key)
    return next((i + 1 for i, key in enumerate(seen) if key in want), None)


def evaluate(retriever, rows, k: int = 5, pool: int = 50) -> dict:
    out = defaultdict(lambda: defaultdict(list))
    detail = []
    for r in rows:
        hits = retriever.search(r["q"], pool)
        if r["tier"] == "abstain" or not r["gold"]:
            detail.append((r["id"], "abstain", hits[0] if hits else None))
            continue
        rk = rank_of(hits, r["gold"])
        detail.append((r["id"], rk, hits[0] if hits else None))
        for grp in ("all", r["style"], r["tier"], r["split"]):
            out[grp]["hit"].append(rk is not None and rk <= k)
            out[grp]["rr"].append(1 / rk if rk else 0.0)
    return {g: {"n": len(v["hit"]), f"recall@{k}": sum(v["hit"]) / len(v["hit"]), "mrr": sum(v["rr"]) / len(v["rr"])}
            for g, v in out.items()}, detail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"])
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--mode", choices=["lexical", "dense", "hybrid"], default="lexical")
    ap.add_argument("--tag", help="embedding index tag (dense / hybrid)")
    ap.add_argument("--rerank", type=int, metavar="POOL", help="rerank the top POOL hits with the cross-encoder")
    ap.add_argument("--reranker", choices=["local", "server"], default="local")
    ap.add_argument("--quiet", action="store_true", help="summary only")
    a = ap.parse_args()
    rows = [json.loads(l) for l in EVAL.read_text(encoding="utf-8").splitlines() if l.strip()]
    if a.split:
        rows = [r for r in rows if r["split"] == a.split]
    lex = LexicalRetriever(a.db)
    if a.mode == "lexical":
        retriever = lex
    else:
        from application.modules.legal_retrieval.dense import DenseRetriever, HybridRetriever
        dense = DenseRetriever(a.tag, a.db)
        retriever = dense if a.mode == "dense" else HybridRetriever(lex, dense)
    if a.rerank:
        from application.modules.legal_retrieval.rerank import RerankedRetriever, ServerReranker
        retriever = RerankedRetriever(retriever, ServerReranker() if a.reranker == "server" else None, pool=a.rerank)
    stats, detail = evaluate(retriever, rows, a.k, pool=a.k if a.rerank else 50)
    for g, s in stats.items():
        print(f"{g:12} n={s['n']:2}  recall@{a.k}={s[f'recall@{a.k}']:.3f}  mrr={s['mrr']:.3f}")
    if a.quiet:
        return
    print("\nper question (rank of gold; - = not in top 50; abstain rows are unscored):")
    for qid, rk, top in detail:
        t = f"{top.law} Điều {top.dieu_no}" if top else "no hit"
        label = "abstain" if rk == "abstain" else (rk or "-")
        print(f"  {qid:9} rank={label:>7}   top: {t}")


if __name__ == "__main__":
    main()
