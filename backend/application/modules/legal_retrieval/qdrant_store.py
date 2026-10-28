"""Dense statute search on Qdrant in embedded mode: a folder under backend/cache, no server to run.

Same vectors as dense.py. `index` loads vec_<tag>.npy into collection chunks_<tag>: one point per chunk, point id =
chunks.id, the law as payload, so a law filter runs inside Qdrant instead of row by row. QdrantRetriever is a drop-in
for DenseRetriever (also inside HybridRetriever); texts and offsets still come from the SQLite KB, Qdrant only holds
vectors. Embedded Qdrant locks its folder, so one process at a time; clients are shared within a process.

    python -m application.modules.legal_retrieval.qdrant_store index --tag 80m
    python -m application.modules.legal_retrieval.qdrant_store search "cho thuê lại nhà ở" --tag 80m
"""
import argparse
import atexit
import json
import re
import sqlite3
from functools import lru_cache
from pathlib import Path

import numpy as np
from qdrant_client import QdrantClient, models

from application.modules.legal_retrieval.dense import CACHE, Embedder
from application.modules.legal_retrieval.kb import DEFAULT_DB, hits_for
from application.modules.legal_retrieval.retriever import Hit

QDRANT_DIR = CACHE / "qdrant"


@lru_cache(maxsize=None)
def client(path: Path = QDRANT_DIR) -> QdrantClient:
    cl = QdrantClient(path=str(path))
    atexit.register(cl.close)       # its own __del__ runs too late at interpreter exit and prints a traceback
    return cl


def collection(tag: str) -> str:
    return "chunks_" + re.sub(r"[^A-Za-z0-9_-]", "_", tag)


def _chunk_count(con: sqlite3.Connection) -> int:
    return con.execute("SELECT count(*) FROM chunks").fetchone()[0]


def index(tag: str, db_path: Path = DEFAULT_DB, path: Path = QDRANT_DIR, cache: Path = CACHE) -> dict:
    """(Re)build collection chunks_<tag> from vec_<tag>.npy; run again after the KB or the vectors change."""
    mat = np.load(cache / f"vec_{tag}.npy")
    con = sqlite3.connect(db_path)
    laws = [r[0] for r in con.execute(
        "SELECT a.law FROM chunks c JOIN articles a ON a.id = c.article_id ORDER BY c.id")]
    if len(laws) != len(mat):
        raise RuntimeError(f"vec_{tag} has {len(mat)} rows but the KB has {len(laws)} chunks; re-run dense embed")
    cl, name = client(path), collection(tag)
    if cl.collection_exists(name):
        cl.delete_collection(name)
    cl.create_collection(name, vectors_config=models.VectorParams(size=mat.shape[1], distance=models.Distance.COSINE))
    cl.upload_collection(name, vectors=mat, payload=[{"law": l} for l in laws], ids=list(range(len(laws))))
    return {"collection": name, "points": cl.count(name, exact=True).count, "dim": int(mat.shape[1])}


class QdrantRetriever:
    def __init__(self, tag: str, db_path: Path = DEFAULT_DB, embedder: Embedder | None = None,
                 path: Path = QDRANT_DIR, cache: Path = CACHE):
        self.con = sqlite3.connect(db_path)
        self.meta = json.loads((cache / f"vec_{tag}.json").read_text(encoding="utf-8"))
        self.client, self.name = client(path), collection(tag)
        if not self.client.collection_exists(self.name):
            raise RuntimeError(f"no Qdrant collection {self.name}; run qdrant_store index --tag {tag}")
        n, have = _chunk_count(self.con), self.client.count(self.name, exact=True).count
        if n != have:
            raise RuntimeError(f"{self.name} has {have} points but the KB has {n} chunks; re-run qdrant_store index")
        self.emb = embedder or Embedder(self.meta["model"], self.meta["dim"], bf16=self.meta.get("bf16", False))

    def search(self, query: str, k: int = 5, law: str | None = None) -> list[Hit]:
        flt = models.Filter(must=[models.FieldCondition(key="law", match=models.MatchValue(value=law))]) if law else None
        pts = self.client.query_points(self.name, query=self.emb.encode_query(query).tolist(), limit=k,
                                       query_filter=flt).points
        return hits_for(self.con, [(int(p.id), float(p.score)) for p in pts])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["index", "search"])
    ap.add_argument("query", nargs="?")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--law")
    ap.add_argument("-k", type=int, default=5)
    a = ap.parse_args()
    if a.cmd == "index":
        print(index(a.tag))
        return
    for h in QdrantRetriever(a.tag).search(a.query, a.k, a.law):
        print(f"  {h.score:6.3f}  {h.law} Điều {h.dieu_no} [{h.ref or '-'}]  {h.text.splitlines()[-1][:90]}")


if __name__ == "__main__":
    main()
