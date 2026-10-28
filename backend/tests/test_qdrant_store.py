import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import numpy as np

from application.modules.legal_retrieval import kb
from application.modules.legal_retrieval import qdrant_store as qs
from application.modules.legal_retrieval.dense import HybridRetriever
from tests.test_legal_kb import LAW


class OneHot:
    """Stands in for Embedder: the query vector points straight at one chunk."""

    def __init__(self, n: int, target: int):
        self.n, self.target = n, target

    def encode_query(self, q: str) -> np.ndarray:
        v = np.zeros(self.n, dtype=np.float32)
        v[self.target] = 1.0
        return v


class Qdrant(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        (d / "luat_thu.txt").write_text(LAW, encoding="utf-8")
        (d / "luat_khac.txt").write_text(LAW, encoding="utf-8")
        cls.db = d / "kb.db"
        kb.build([d], cls.db)
        cls.n = sqlite3.connect(cls.db).execute("SELECT count(*) FROM chunks").fetchone()[0]
        np.save(d / "vec_t.npy", np.eye(cls.n, dtype=np.float32))
        (d / "vec_t.json").write_text(json.dumps({"model": "fake", "dim": cls.n}), encoding="utf-8")
        cls.store, cls.cache = d / "qdrant", d
        cls.info = qs.index("t", cls.db, cls.store, cls.cache)

    @classmethod
    def tearDownClass(cls):
        qs.client(cls.store).close()
        cls.tmp.cleanup()

    def retriever(self, target: int) -> qs.QdrantRetriever:
        return qs.QdrantRetriever("t", self.db, OneHot(self.n, target), self.store, self.cache)

    def law_of(self, cid: int) -> str:
        return sqlite3.connect(self.db).execute(
            "SELECT a.law FROM chunks c JOIN articles a ON a.id = c.article_id WHERE c.id = ?", (cid,)).fetchone()[0]

    def test_one_point_per_chunk(self):
        self.assertEqual(self.info["points"], self.n)

    def test_nearest_chunk_comes_first_with_its_kb_text(self):
        hit = self.retriever(3).search("anything", 2)[0]
        self.assertEqual(hit.chunk_id, 3)
        self.assertAlmostEqual(hit.score, 1.0, places=5)
        self.assertEqual(hit.law, self.law_of(3))

    def test_law_filter_runs_in_qdrant(self):
        other = "luat_khac" if self.law_of(0) == "luat_thu" else "luat_thu"
        hits = self.retriever(0).search("anything", 5, law=other)
        self.assertTrue(hits)
        self.assertTrue(all(h.law == other for h in hits))

    def test_plugs_into_hybrid(self):
        hits = HybridRetriever(kb.LexicalRetriever(self.db), self.retriever(1)).search("cho thuê lại", 3)
        self.assertTrue(hits)

    def test_stale_collection_fails_loudly(self):
        d = Path(self.tmp.name)
        np.save(d / "vec_s.npy", np.eye(self.n - 1, self.n, dtype=np.float32))
        with self.assertRaisesRegex(RuntimeError, "re-run dense embed"):
            qs.index("s", self.db, self.store, self.cache)
