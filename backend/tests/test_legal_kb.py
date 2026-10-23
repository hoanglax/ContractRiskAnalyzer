import tempfile
import unittest
from pathlib import Path

from application.modules.legal_retrieval import eval as leval
from application.modules.legal_retrieval import kb
from application.modules.legal_retrieval.chunk import khoan_split
from tests.data_paths import DATA

LAW = """LUẬT THỬ NGHIỆM

Điều 1. Phạm vi điều chỉnh
Luật này quy định về cho thuê nhà ở.
Điều 2. Quyền của bên thuê
1. Bên thuê có quyền sử dụng nhà ở đúng mục đích.
2. Bên thuê có quyền cho thuê lại nếu được bên cho thuê đồng ý.
Điều 3. Nghĩa vụ của bên thuê
1. Bên thuê phải trả tiền thuê đúng hạn.
2. Bên thuê phải giữ gìn nhà ở.
a) không tự ý sửa chữa;
b) không chuyển nhượng.
Điều 4. Chấm dứt hợp đồng
Hợp đồng chấm dứt khi hết thời hạn thuê.
"""


class Chunking(unittest.TestCase):
    def test_no_khoan_is_one_block(self):
        self.assertEqual(khoan_split("Điều 1. X", "Nội dung.\nThêm."), [("", "Điều 1. X\nNội dung.\nThêm.")])

    def test_khoan_units_carry_the_heading(self):
        out = khoan_split("Điều 2. X", "1. Một.\n2. Hai.")
        self.assertEqual([r for r, _ in out], ["1", "2"])
        self.assertTrue(all(t.startswith("Điều 2. X\n") for _, t in out))

    def test_long_khoan_splits_by_diem(self):
        body = "1. Lead-in:\na) " + "x " * 200 + "\nb) " + "y " * 200
        out = khoan_split("Điều 5. X", body, maxchars=100)
        self.assertEqual([r for r, _ in out], ["1.a", "1.b"])
        self.assertIn("Lead-in", out[0][1])

    def test_diem_directly_under_dieu(self):
        out = khoan_split("Điều 6. X", "a) Một.\nb) Hai.")
        self.assertEqual([r for r, _ in out], ["a", "b"])


class Kb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        (d / "luat_thu.txt").write_text(LAW, encoding="utf-8")
        cls.db = d / "kb.db"
        cls.info = kb.build([d], cls.db)
        cls.corpus = [d]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_counts_and_verbatim_offsets(self):
        self.assertEqual(self.info["per_law"], {"luat_thu": 4})
        self.assertEqual(self.info["articles"], 4)
        self.assertEqual(kb.verify(self.db, self.corpus), [])

    def test_search_finds_the_khoan(self):
        with kb.LexicalRetriever(self.db) as retriever:
            hit = retriever.search(
                "cho thuê lại cần bên cho thuê đồng ý", 3
            )[0]

        self.assertEqual(
            (hit.law, hit.dieu_no, hit.ref),
            ("luat_thu", 2, "2"),
        )


    def test_law_filter_and_diacritics_are_folded(self):
        with kb.LexicalRetriever(self.db) as retriever:
            self.assertTrue(
                retriever.search("cham dut hop dong", 3, law="luat_thu")
            )
            self.assertEqual(
                retriever.search("cham dut hop dong", 3, law="khac"),
                [],
            )

    def test_empty_query(self):
        with kb.LexicalRetriever(self.db) as retriever:
            self.assertEqual(retriever.search("   ", 3), [])

    def test_no_dieu_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "x.txt").write_text("không có điều khoản nào " * 40, encoding="utf-8")
            with self.assertRaises(ValueError):
                kb.build([Path(d)], Path(d) / "k.db")


class Eval(unittest.TestCase):
    def test_rank_dedupes_by_article(self):
        class H:
            def __init__(self, law, dieu): self.law, self.dieu_no = law, dieu
        hits = [H("a", 1), H("a", 1), H("b", 2)]
        self.assertEqual(leval.rank_of(hits, [{"law": "b.txt", "dieu": 2}]), 2)
        self.assertIsNone(leval.rank_of(hits, [{"law": "c.txt", "dieu": 9}]))


@unittest.skipUnless((DATA.parent / "legal_corpus").exists(), "data/legal_corpus not present")
class RealCorpus(unittest.TestCase):
    def test_taxonomy_citations_resolve(self):
        """The articles the taxonomy cites from the newly fetched laws exist in the built KB."""
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "kb.db"
            kb.build([DATA.parent / "legal_corpus"], db)
            
            import sqlite3

            con = sqlite3.connect(db)
            try:
                for law, n in (
                    ("luat_cu_tru_68_2020", 27),
                    ("luat_cu_tru_68_2020", 28),
                    ("luat_cu_tru_68_2020", 30),
                    ("luat_quan_ly_thue_108_2025", 26),
                ):
                    self.assertTrue(
                        con.execute(
                            "SELECT 1 FROM articles WHERE law=? AND dieu_no=?",
                            (law, n),
                        ).fetchone(),
                        (law, n),
                    )

                self.assertEqual(
                    kb.verify(db, [DATA.parent / "legal_corpus"]),
                    [],
                )
            finally:
                con.close()



if __name__ == "__main__":
    unittest.main()
