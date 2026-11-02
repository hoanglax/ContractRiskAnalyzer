"""Dense half of statute retrieval: embed every chunk, brute-force cosine search over a numpy matrix.

~5k chunks x <=2048 floats is tens of MB, so no vector database is needed (see kb.py). Vectors are
row-aligned with `chunks.id` and stored as backend/cache/vec_<tag>.npy (+ .json with the model, the
dimension and `kb_sha`, a hash of the chunk texts they were made from, so vectors from another KB fail
loudly instead of returning nonsense).

The demo index (80m) is committed in data/legal_vectors, so the Docker build and a fresh setup copy it
instead of embedding. After changing data/legal_corpus, re-embed it and commit the result:
    python -m application.modules.legal_retrieval.kb build
    python -m application.modules.legal_retrieval.dense embed --model codefuse-ai/F2LLM-v2-80M --tag 80m --out ../data/legal_vectors

Embedders: the F2LLM-v2 family (codefuse-ai/F2LLM-v2-{80M,160M,330M,0.6B,1.7B,...}): last-token pooling,
L2-normalised, queries get an instruction prefix and documents get none. Its vectors are Matryoshka
trained, so `dim` may truncate them (re-normalised) to shrink the index.

    python -m application.modules.legal_retrieval.dense embed --model codefuse-ai/F2LLM-v2-330M [--dim 256] [--tag 330m]
    python -m application.modules.legal_retrieval.dense search "cho thuê lại nhà ở" --tag 330m
"""
import argparse
import hashlib
import json
import sqlite3
import time
from pathlib import Path

import numpy as np

from application.modules.legal_retrieval.kb import DEFAULT_DB, LexicalRetriever, hits_for
from application.modules.legal_retrieval.retriever import Hit

CACHE = DEFAULT_DB.parent
COMMITTED = DEFAULT_DB.parents[2] / "data" / "legal_vectors"


def kb_fingerprint(con: sqlite3.Connection) -> str:
    """sha256 of the chunk texts in id order: what the vectors are row-aligned with."""
    h = hashlib.sha256()
    for (text,) in con.execute("SELECT text FROM chunks ORDER BY id"):
        h.update(text.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def check_kb(tag: str, meta: dict, con: sqlite3.Connection, rows: int) -> None:
    """Raise if vec_<tag> was not embedded from this KB (row count; and kb_sha when the index records one)."""
    n = con.execute("SELECT count(*) FROM chunks").fetchone()[0]
    redo = f"re-run dense embed: python -m application.modules.legal_retrieval.dense embed --model {meta.get('model')} --tag {tag}"
    if n != rows:
        raise RuntimeError(f"vec_{tag} has {rows} rows but the KB has {n} chunks; {redo}")
    if meta.get("kb_sha") and meta["kb_sha"] != kb_fingerprint(con):
        raise RuntimeError(f"vec_{tag} was embedded from a different KB (the legal corpus changed); {redo}")
QUERY_PROMPT = "Instruct: Given a question, retrieve passages that can help answer the question.\nQuery: "


class Embedder:
    def __init__(self, model_id: str, dim: int | None = None, max_len: int = 512, bf16: bool = False):
        import torch
        from transformers import AutoModel, AutoTokenizer
        self.torch, self.model_id, self.dim, self.max_len = torch, model_id, dim, max_len
        self.tok = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModel.from_pretrained(model_id, dtype=torch.bfloat16 if bf16 else torch.float32).eval()
        self._queries: dict[str, np.ndarray] = {}

    def encode(self, texts: list[str], batch: int = 16, prefix: str = "") -> np.ndarray:
        torch = self.torch
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))      # similar lengths pad less
        out = [None] * len(texts)
        with torch.inference_mode():
            for b in range(0, len(order), batch):
                idx = order[b:b + batch]
                enc = self.tok([prefix + texts[i] for i in idx], padding=True, truncation=True,
                               max_length=self.max_len, return_tensors="pt")
                h = self.model(**enc).last_hidden_state
                last = enc["attention_mask"].sum(dim=1) - 1                  # right padding: last real token
                v = h[torch.arange(len(idx)), last].float()
                if self.dim:
                    v = v[:, :self.dim]
                v = torch.nn.functional.normalize(v, dim=1).numpy()
                for j, i in enumerate(idx):
                    out[i] = v[j]
        return np.stack(out)

    def encode_query(self, q: str) -> np.ndarray:
        # one finding searches several laws with the same query: embed it once
        if q not in self._queries:
            if len(self._queries) >= 1024:
                self._queries.clear()
            self._queries[q] = self.encode([q], prefix=QUERY_PROMPT)[0]
        return self._queries[q]


def embed_index(model_id: str, tag: str, dim: int | None = None, db_path: Path = DEFAULT_DB,
                bf16: bool = False, out: Path = CACHE) -> dict:
    con = sqlite3.connect(db_path)
    rows = con.execute("SELECT id, text FROM chunks ORDER BY id").fetchall()
    assert [r[0] for r in rows] == list(range(len(rows))), "chunk ids must be 0..N-1"
    emb = Embedder(model_id, dim, bf16=bf16)
    t = time.time()
    mat = emb.encode([r[1] for r in rows])
    secs = time.time() - t
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / f"vec_{tag}.npy", mat)
    meta = {"model": model_id, "dim": int(mat.shape[1]), "n": len(rows), "seconds": round(secs, 1), "bf16": bf16,
            "kb_sha": kb_fingerprint(con)}
    (out / f"vec_{tag}.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    return meta


class DenseRetriever:
    def __init__(self, tag: str, db_path: Path = DEFAULT_DB, embedder: Embedder | None = None):
        self.con = sqlite3.connect(db_path)
        self.mat = np.load(CACHE / f"vec_{tag}.npy")
        self.meta = json.loads((CACHE / f"vec_{tag}.json").read_text(encoding="utf-8"))
        check_kb(tag, self.meta, self.con, len(self.mat))
        self.emb = embedder or Embedder(self.meta["model"], self.meta["dim"], bf16=self.meta.get("bf16", False))

    def search(self, query: str, k: int = 5, law: str | None = None) -> list[Hit]:
        sims = self.mat @ self.emb.encode_query(query)
        order = np.argsort(-sims)
        out = []
        for cid in order:
            if law is not None and self.con.execute(
                    "SELECT a.law FROM chunks c JOIN articles a ON a.id=c.article_id WHERE c.id=?", (int(cid),)
            ).fetchone()[0] != law:
                continue
            out.append((int(cid), float(sims[cid])))
            if len(out) == k:
                break
        return hits_for(self.con, out)


class HybridRetriever:
    """Reciprocal-rank fusion of the lexical and dense rankings (rank constant 60)."""

    def __init__(self, lexical: LexicalRetriever, dense: DenseRetriever, pool: int = 50, rrf_k: int = 60):
        self.lexical, self.dense, self.pool, self.rrf_k = lexical, dense, pool, rrf_k

    def search(self, query: str, k: int = 5, law: str | None = None) -> list[Hit]:
        score: dict[int, float] = {}
        for ranking in (self.lexical.search(query, self.pool, law), self.dense.search(query, self.pool, law)):
            for r, h in enumerate(ranking):
                score[h.chunk_id] = score.get(h.chunk_id, 0.0) + 1.0 / (self.rrf_k + r + 1)
        best = sorted(score.items(), key=lambda kv: -kv[1])[:k]
        return hits_for(self.lexical.con, best)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["embed", "search"])
    ap.add_argument("query", nargs="?")
    ap.add_argument("--model")
    ap.add_argument("--tag", required=False)
    ap.add_argument("--dim", type=int)
    ap.add_argument("--bf16", action="store_true")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--out", type=Path, default=CACHE, help="where vec_<tag>.* go (default backend/cache)")
    ap.add_argument("-k", type=int, default=5)
    a = ap.parse_args()
    if a.cmd == "embed":
        tag = a.tag or a.model.rsplit("-", 1)[-1].lower()
        print(embed_index(a.model, tag, a.dim, a.db, bf16=a.bf16, out=a.out))
        return
    for h in DenseRetriever(a.tag).search(a.query, a.k):
        print(f"  {h.score:6.3f}  {h.law} Điều {h.dieu_no} [{h.ref or '-'}]  {h.text.splitlines()[-1][:90]}")


if __name__ == "__main__":
    main()
