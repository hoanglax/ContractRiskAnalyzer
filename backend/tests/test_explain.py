import json
import os
import unittest
from unittest import mock

from application.adapters.llm import LLMError, LLMResult
from application.modules.detection.finding import Finding
from application.modules.explain import explain as ex
from application.modules.ingestion.ingest import ingest
from application.modules.legal_basis.basis import LegalBasis
from application.modules.taxonomy.taxonomy import Risk, Taxonomy

TEXT = """HỢP ĐỒNG THUÊ PHÒNG
Điều 1. Tiền cọc
Bên B đặt cọc 2 tháng. Bên A tự xác định thiệt hại để trừ vào tiền cọc theo báo giá do Bên A chọn.
Điều 2. Lãi chậm trả
Bên B chậm trả thì chịu lãi 2% mỗi ngày.
Điều 3. Điều khoản chung
Hai bên cam kết thực hiện đúng các điều khoản trên; hợp đồng lập thành 02 bản có giá trị như nhau, mỗi bên giữ 01 bản."""


def row(code, severity, party):
    return Risk(code=code, party=party, group=code.split("-")[1], name=f"tên {code}", severity=severity, signs="",
                legal_basis="", consequences=[f"hậu quả {code}"])


TAX = Taxonomy({}, {}, [], [row("A-DEP-02", "HIGH", "A"), row("B-DEP-02", "HIGH", "B"), row("B-PEN-04", "CRITICAL", "B"),
                            row("B-DEP-06", "HIGH", "B"), row("B-TRM-06", "LOW", "B")], [])
B328 = LegalBasis("blds_2015", 328, "2", "Điều 328. Đặt cọc ...", "w", "taxonomy", 10)
B468 = LegalBasis("blds_2015", 468, "1", "Điều 468. Lãi suất ...", "w", "taxonomy", 20)


def doc():
    with mock.patch.dict(os.environ, {"STRUCTURE_LLM": "off"}):
        return ingest(TEXT.encode(), "c.txt")


def present(d, code, quote, affects):
    s = d.text.index(quote)
    return Finding(kind="present", issue=f"vấn đề {code}", code=code, quote=quote, affects=affects,
                   char_start=s, char_end=s + len(quote), clause=None)


class Group(unittest.TestCase):
    def test_overlapping_quotes_become_one_item_and_missing_stay_apart(self):
        d = doc()
        fs = [present(d, "B-DEP-06", "chịu lãi 2% mỗi ngày", "lessee"),
              present(d, "A-DEP-02", "Bên A tự xác định thiệt hại để trừ vào tiền cọc", "lessor"),
              present(d, "B-PEN-04", "trừ vào tiền cọc theo báo giá do Bên A chọn.", "lessee"),
              present(d, "B-DEP-02", "Bên A tự xác định thiệt hại", "lessee"),
              Finding(kind="missing", issue="thiếu hiện trạng", code="B-TRM-06", affects="lessee")]
        bases = [{"basis": [B468]}, {"basis": [B328]}, {"basis": [B328]}, {"basis": []}, {"basis": []}]
        items = ex.group(d, fs, bases, TAX)
        self.assertEqual([it.codes for it in items], [["A-DEP-02", "B-DEP-02", "B-PEN-04"], ["B-DEP-06"], ["B-TRM-06"]])
        first = items[0]
        self.assertEqual(first.quote, "Bên A tự xác định thiệt hại để trừ vào tiền cọc theo báo giá do Bên A chọn.")
        self.assertEqual((first.severity, first.parties), ("CRITICAL", ["lessee", "lessor"]))
        self.assertEqual([b.chunk_id for b in first.basis], [10])          # one passage, cited by two codes
        self.assertIsNone(items[2].quote)


class Check(unittest.TestCase):
    def setUp(self):
        self.it = ex.Item(kind="present", codes=["B-DEP-06"], severity="HIGH", parties=["lessee"],
                          issues={"B-DEP-06": "x"}, basis=[B468])

    def reply(self, summary, rec="Đề nghị sửa Điều 2 của hợp đồng về mức lãi."):
        return json.dumps({"summary": summary, "recommendation": rec}, ensure_ascii=False)

    def test_l_refs_become_citations_and_contract_clauses_are_fine(self):
        e, why = ex.check(self.reply("Lãi 2%/ngày vượt mức trần [L1]."), self.it)
        self.assertIsNone(why)
        self.assertEqual(e.summary, "Lãi 2%/ngày vượt mức trần (Bộ luật Dân sự 2015, Điều 468, khoản 1).")
        self.assertEqual(e.cited, ["Bộ luật Dân sự 2015, Điều 468, khoản 1"])

    def test_unknown_ref_or_self_written_article_drops_it(self):
        self.assertIsNone(ex.check(self.reply("Trái [L2]."), self.it)[0])
        e, why = ex.check(self.reply("Trái Điều 357 Bộ luật Dân sự."), self.it)
        self.assertIsNone(e)
        self.assertIn("Điều 357", why)
        self.assertIsNotNone(ex.check(self.reply("Vượt trần theo Điều 468 Bộ luật Dân sự."), self.it)[0])   # in the list

    def test_labels_read_like_citations(self):
        from application.modules.legal_basis.basis import ref_name
        self.assertEqual([ref_name(r) for r in ("2", "2.a", "c", "")], ["khoản 2", "khoản 2, điểm a", "điểm c", ""])

    def test_garbage_is_dropped(self):
        self.assertEqual(ex.check("không biết", self.it), (None, "unparseable explain reply"))
        self.assertIsNone(ex.check(json.dumps({"summary": "x", "recommendation": ""}), self.it)[0])


class Explain(unittest.TestCase):
    def test_one_call_per_item_and_failures_keep_the_item(self):
        d = doc()
        fs = [present(d, "B-DEP-06", "chịu lãi 2% mỗi ngày", "lessee"),
              Finding(kind="missing", issue="thiếu hiện trạng", code="B-TRM-06", affects="lessee")]
        good = LLMResult(json.dumps({"summary": "Lãi quá cao [L1].", "recommendation": "Đề nghị giảm."}), "stop", {}, "p", "m")
        with mock.patch.object(ex.llm, "chat", side_effect=[good, LLMError("p: HTTP 503")]) as chat:
            out = ex.explain(d, fs, [{"basis": [B468]}, {"basis": []}], tax=TAX)
        self.assertEqual(chat.call_count, 2)
        a, b = out["items"]
        self.assertIn("Điều 468", a.explanation.summary)
        self.assertIn("[L1] Bộ luật Dân sự 2015, Điều 468, khoản 1", chat.call_args_list[0].args[1][0]["content"])
        self.assertIn("Danh sách trống", chat.call_args_list[1].args[1][0]["content"])
        self.assertIsNone(b.explanation)
        self.assertIn("HTTP 503", b.warnings[0])


if __name__ == "__main__":
    unittest.main()
