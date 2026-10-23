"""Run every retrieval configuration against the eval set and print one comparison table.

    python -m application.modules.legal_retrieval.bench [--k 5] [--json OUT]

Configurations: lexical with each tokenizer (pairs | pyvi | both), dense per embedding index
(backend/cache/vec_*.npy), and hybrid (RRF) of each dense index with each lexical index. Reports
recall@k / MRR overall and by tier, query latency, index size and (from the .json beside each .npy)
the CPU time it took to embed the corpus.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from application.modules.legal_retrieval import eval as leval
from application.modules.legal_retrieval.kb import DEFAULT_DB, LexicalRetriever

CACHE = DEFAULT_DB.parent
TOKENIZERS = ("pairs", "pyvi", "both")


def lexical_db(tok: str) -> Path:
    path = CACHE / f"legal_kb_{tok}.db"
    if not path.exists():                                   # tokenizer is read at import, so build in a child
        env = {**os.environ, "KB_TOKENIZER": tok}
        subprocess.run([sys.executable, "-m", "application.modules.legal_retrieval.kb", "build", "--db", str(path)], env=env,
                       check=True, capture_output=True)
    return path


def timed(retriever, rows, k):
    t = time.time()
    stats, _ = leval.evaluate(retriever, rows, k)
    return stats, (time.time() - t) / max(len(rows), 1) * 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    from application.modules.legal_retrieval.dense import DenseRetriever, HybridRetriever
    rows = [json.loads(l) for l in leval.EVAL.read_text(encoding="utf-8").splitlines() if l.strip()]
    key = f"recall@{a.k}"
    results = []

    def record(name, stats, ms, extra=None):
        g = lambda grp, f: stats.get(grp, {}).get(f)
        results.append({"config": name, "all": g("all", key), "mrr": g("all", "mrr"),
                        "question": g("question", key), "title_match": g("title_match", key),
                        "rd_anchor": g("rd_anchor", key), "dev": g("dev", key), "test": g("test", key),
                        "ms_per_query": round(ms), **(extra or {})})

    # Each tokenizer needs its own process (the tokenizer is chosen at import), so score lexical in children.
    lex = {}
    for tok in TOKENIZERS:
        env = {**os.environ, "KB_TOKENIZER": tok}
        db = lexical_db(tok)
        out = subprocess.run([sys.executable, "-c", (
            "import json,sys;from application.modules.legal_retrieval import eval as e;from application.modules.legal_retrieval.kb import LexicalRetriever;"
            f"rows=[json.loads(l) for l in e.EVAL.read_text(encoding='utf-8').splitlines() if l.strip()];"
            f"s,_=e.evaluate(LexicalRetriever(r'{db}'),rows,{a.k});print(json.dumps(s))")],
            env=env, check=True, capture_output=True, text=True).stdout
        record(f"lexical/{tok}", json.loads(out.strip().splitlines()[-1]), 0)
        lex[tok] = db

    tags = sorted(p.stem[4:] for p in CACHE.glob("vec_*.npy"))
    for tag in tags:
        meta = json.loads((CACHE / f"vec_{tag}.json").read_text(encoding="utf-8"))
        extra = {"dim": meta["dim"], "embed_s": meta["seconds"], "index_mb": round((CACHE / f"vec_{tag}.npy").stat().st_size / 2**20, 1)}
        dense = DenseRetriever(tag, DEFAULT_DB)
        stats, ms = timed(dense, rows, a.k)
        record(f"dense/{tag}", stats, ms, extra)
        for tok in ("pairs", "pyvi"):
            # chunk ids do not depend on the tokenizer, so the dense matrix lines up with any lexical db
            d2 = DenseRetriever(tag, lex[tok], embedder=dense.emb)
            hyb = HybridRetriever(LexicalRetriever(lex[tok]), d2)
            stats, ms = timed(hyb, rows, a.k)
            record(f"hybrid/{tag}+{tok}", stats, ms, extra)

    cols = ["config", "all", "mrr", "question", "title_match", "rd_anchor", "dev", "test", "ms_per_query", "dim", "embed_s", "index_mb"]
    print("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols))
    for r in results:
        print("| " + " | ".join("" if r.get(c) is None else (f"{r[c]:.3f}" if isinstance(r[c], float) else str(r[c])) for c in cols) + " |")
    if a.json:
        a.json.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
