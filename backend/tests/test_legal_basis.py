import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from application.adapters.llm import LLMResult
from application.modules.detection.finding import Finding
from application.modules.legal_basis import basis
from application.modules.legal_retrieval.kb import SCHEMA
from application.modules.legal_retrieval.retriever import Hit
from application.modules.taxonomy.taxonomy import Risk, Taxonomy

# law, dieu, ref, text
CHUNKS = [("luat_nha_o_2023", 172, "khoản 1", "Điều 172. Đơn phương chấm dứt. 1. Bên cho thuê được đơn phương chấm dứt khi bên thuê không trả tiền thuê từ 03 tháng trở lên."),
          ("luat_nha_o_2023", 172, "khoản 2", "Điều 172. 2. Bên thuê được đơn phương chấm dứt khi bên cho thuê không sửa chữa nhà."),
          ("luat_nha_o_2023", 172, "khoản 4", "Điều 172. 4. Bên đơn phương chấm dứt phải báo trước ít nhất 30 ngày."),
          ("blds_2015", 468, "", "Điều 468. Lãi suất không vượt quá 20%/năm."),
          ("nd96_2024_fuluc2_hop_dong_thue_nha_o", 9, "", "Điều 9. Mẫu hợp đồng: chấm dứt hợp đồng.")]


def make_kb(path: Path):
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    arts = {}
    for i, (law, dieu, ref, text) in enumerate(CHUNKS):
        aid = arts.setdefault((law, dieu), len(arts))
        con.execute("INSERT OR IGNORE INTO articles VALUES (?,?,?,?,?,?,?)", (aid, law, dieu, f"Điều {dieu}", text, 0, 1))
        con.execute("INSERT INTO chunks VALUES (?,?,?,?)", (i, aid, ref, text))
    con.commit()
    con.close()


class FakeRetriever:
    """Ranks chunks by a fixed order; `law` filters like the real ones."""
    def __init__(self, order):
        self.order = order

    def search(self, query, k=5, law=None):
        hits = [Hit(i, i, CHUNKS[i][0], CHUNKS[i][1], CHUNKS[i][2], 1.0, CHUNKS[i][3]) for i in self.order]
        return [h for h in hits if law in (None, h.law)][:k]


def risk(citations):
    return Risk(code="B-TRM-01", party="B", group="TRM", name="Bị chấm dứt hợp đồng trước thời hạn không có căn cứ",
                severity="HIGH", signs="", legal_basis="", citations=citations)


FINDING = Finding(kind="present", issue="Chấm dứt khi chậm trả 5 ngày", code="B-TRM-01",
                  quote="Bên A có quyền đơn phương chấm dứt Hợp Đồng")


def reply(obj):
    return LLMResult(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False), "stop", {}, "p", "m")


class Candidates(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.db = Path(d.name) / "kb.db"
        make_kb(self.db)
        self.con = sqlite3.connect(self.db)
        self.addCleanup(self.con.close)

    def test_cited_article_first_best_khoan_first_then_retrieval_without_duplicates_or_templates(self):
        r = risk([{"law": "luat_nha_o_2023", "dieu": [172], "text": "Điều 172 Luật Nhà ở 2023"}])
        cands, warnings = basis.candidates(FINDING, r, FakeRetriever([2, 4, 0, 3]), self.con)
        self.assertEqual(warnings, [])
        self.assertEqual([(c.hit.chunk_id, c.source) for c in cands],
                         [(2, "taxonomy"), (0, "taxonomy"), (1, "taxonomy"), (3, "retrieval")])
        self.assertEqual([c.id for c in cands], ["C1", "C2", "C3", "C4"])     # chunk 4 (model contract) left out

    def test_law_without_article_is_searched_within_the_law_and_unknown_laws_warn(self):
        r = risk([{"law": "blds_2015", "dieu": [], "text": "BLDS 2015"},
                  {"law": None, "dieu": [5], "text": "Luật X 2099 Điều 5"},
                  {"law": "blds_2015", "dieu": [999], "text": "Điều 999 BLDS"}])
        cands, warnings = basis.candidates(FINDING, r, FakeRetriever([3]), self.con)
        self.assertEqual([(c.hit.law, c.source) for c in cands], [("blds_2015", "taxonomy")])
        self.assertEqual(len(warnings), 2)
        self.assertIn("Luật X 2099", warnings[0])
        self.assertIn("Điều 999 is not in the KB", warnings[1])

    def test_missing_finding_queries_with_the_risk_name(self):
        f = Finding(kind="missing", issue="Thiếu", code="B-TRM-01")
        self.assertIn("không có căn cứ", basis.query_for(f, risk([])))


class Pick(unittest.TestCase):
    def setUp(self):
        hits = [Hit(i, i, CHUNKS[i][0], CHUNKS[i][1], CHUNKS[i][2], 1.0, CHUNKS[i][3]) for i in (0, 2)]
        self.cands = [basis.Candidate("C1", hits[0], "taxonomy"), basis.Candidate("C2", hits[1], "retrieval")]

    def run_pick(self, reply_obj):
        with mock.patch.object(basis.llm, "chat", return_value=reply(reply_obj)) as chat:
            return basis.pick(FINDING, risk([]), self.cands), chat

    def test_picks_come_from_the_kb_and_unknown_ids_are_dropped(self):
        out, chat = self.run_pick({"basis": [{"id": "C2", "why": "báo trước 30 ngày"}, {"id": "C9", "why": "bịa"},
                                             {"id": "C1", "why": "chỉ khi nợ 3 tháng"}]})
        self.assertEqual([(b.dieu, b.ref, b.source) for b in out["basis"]],
                         [(172, "khoản 4", "retrieval"), (172, "khoản 1", "taxonomy")])
        self.assertEqual(out["basis"][1].text, CHUNKS[0][3])
        self.assertEqual(len(out["warnings"]), 1)
        self.assertIn("C9", out["warnings"][0])
        prompt = chat.call_args.args[1][0]["content"]
        self.assertIn("[C1] luat_nha_o_2023, Điều 172, khoản 1", prompt)
        self.assertEqual(chat.call_args.args[0], "legal_pick")

    def test_plain_id_list_is_the_reply_shape(self):
        out, _ = self.run_pick({"basis": ["C2", "C7"]})
        self.assertEqual([(b.dieu, b.ref, b.why) for b in out["basis"]], [(172, "khoản 4", "")])
        self.assertIn("C7", out["warnings"][0])

    def test_none_fit_is_an_empty_basis_and_garbage_is_a_warning(self):
        out, _ = self.run_pick({"basis": []})
        self.assertEqual((out["basis"], out["warnings"]), ([], []))
        out, _ = self.run_pick("không biết")
        self.assertEqual(out["basis"], [])
        self.assertIn("unparseable", out["warnings"][0])

    def test_no_candidates_means_no_call(self):
        with mock.patch.object(basis.llm, "chat") as chat:
            out = basis.pick(FINDING, risk([]), [])
        chat.assert_not_called()
        self.assertEqual(out["basis"], [])


class Attach(unittest.TestCase):
    def test_one_item_per_finding_in_order(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "kb.db"
            make_kb(db)
            tax = Taxonomy({}, {}, [], [risk([{"law": "luat_nha_o_2023", "dieu": [172], "text": "x"}])], [])
            with mock.patch.object(basis.llm, "chat", return_value=reply({"basis": [{"id": "C1", "why": "w"}]})):
                out = basis.attach([FINDING, FINDING], retriever=FakeRetriever([0, 1, 2, 3]), tax=tax, db_path=db)
        self.assertEqual(out["warnings"], [])
        self.assertEqual([len(i["basis"]) for i in out["items"]], [1, 1])
        self.assertEqual(out["items"][0]["candidates"][0], "luat_nha_o_2023, Điều 172, khoản 1")


if __name__ == "__main__":
    unittest.main()
