import os
import unittest
from unittest import mock

from application.modules.detection.finding import Finding, LookFor, ground, locate
from application.modules.detection.lens import from_taxonomy
from application.modules.ingestion.ingest import ingest
from application.modules.taxonomy import taxonomy as tx

CONTRACT = """HỢP ĐỒNG THUÊ PHÒNG TRỌ
Bên A: Ông ...................... (bên cho thuê)
Bên B: Bà ........................ (bên thuê)
Điều 1. Giá thuê và đặt cọc
Giá thuê là 3.000.000 đồng/tháng, trả trước ngày 05 hằng tháng.
Bên B đặt cọc 2 tháng tiền thuê. Bên B không được nhận lại tiền cọc trong mọi trường hợp.
Điều 2. Chấm dứt hợp đồng
Nếu Bên B chậm trả tiền thuê quá 5 ngày, Bên A có quyền chấm dứt hợp đồng, khóa cửa và dọn đồ ra ngoài.
Bên A được lấy lại phòng bất cứ lúc nào nếu báo trước 7 ngày.
Điều 3. Điều khoản chung
Hai bên cam kết thực hiện đúng các điều khoản trên; hợp đồng lập thành 02 bản, mỗi bên giữ 01 bản.
"""


def doc():
    with mock.patch.dict(os.environ, {"STRUCTURE_LLM": "off"}):
        return ingest(CONTRACT.encode(), "c.txt")


def present(quote, **kw):
    return Finding(kind="present", issue="x", quote=quote, **kw)


class Locate(unittest.TestCase):
    def setUp(self):
        self.text = doc().text

    def test_quote_across_a_line_break_and_typography(self):
        s, e, elided = locate(self.text, "trả trước ngày 05 hằng tháng.  Bên B đặt cọc")
        self.assertIn("05 hằng tháng.\nBên B đặt cọc", self.text[s:e])
        self.assertFalse(elided)

    def test_blanks_in_the_contract_are_not_elisions(self):
        s, e, elided = locate(self.text, "Bên A: Ông ...................... (bên cho thuê)")
        self.assertFalse(elided)
        self.assertTrue(self.text[s:e].startswith("Bên A: Ông"))

    def test_elided_quote_matches_in_order(self):
        s, e, elided = locate(self.text, "Nếu Bên B chậm trả tiền thuê quá 5 ngày … dọn đồ ra ngoài")
        self.assertTrue(elided)
        self.assertTrue(self.text[s:e].startswith("Nếu Bên B") and self.text[s:e].endswith("dọn đồ ra ngoài"))

    def test_elided_pieces_out_of_order_or_too_short_fail(self):
        self.assertIsNone(locate(self.text, "dọn đồ ra ngoài ... Nếu Bên B chậm trả tiền thuê"))
        self.assertIsNone(locate(self.text, "Nếu ... ngoài"))

    def test_rewritten_tone_mark_is_not_the_contract(self):
        self.assertIsNone(locate(self.text, "khoá cửa"))    # contract has "khóa"


class Ground(unittest.TestCase):
    def setUp(self):
        self.doc = doc()

    def test_present_finding_gets_offsets_and_clause(self):
        kept, rejected = ground([present("Bên B không được nhận lại tiền cọc trong mọi trường hợp.", affects="lessee")],
                                self.doc)
        self.assertEqual(rejected, [])
        f = kept[0]
        self.assertEqual(f.clause, "Điều 1")
        self.assertEqual(self.doc.text[f.char_start:f.char_end],
                         "Bên B không được nhận lại tiền cọc trong mọi trường hợp.")

    def test_quote_before_the_first_clause_has_no_clause(self):
        kept, _ = ground([present("HỢP ĐỒNG THUÊ PHÒNG TRỌ")], self.doc)
        self.assertIsNone(kept[0].clause)

    def test_missing_finding_needs_no_quote(self):
        kept, rejected = ground([Finding(kind="missing", issue="Không có điều khoản bàn giao hiện trạng phòng")], self.doc)
        self.assertEqual((len(kept), rejected), (1, []))
        self.assertIsNone(kept[0].char_start)

    def test_rejections(self):
        bad = [present("Bên A được tăng giá bất cứ lúc nào"),            # not in the contract
               present(""),                                             # no quote
               Finding(kind="present", issue=" ", quote="Điều 3. Điều khoản chung"),
               Finding(kind="risky", issue="x"),
               present("Điều 3. Điều khoản chung", affects="Bên B")]    # party as written, not a role
        kept, rejected = ground(bad, self.doc)
        self.assertEqual(kept, [])
        self.assertEqual([why for _, why in rejected],
                         ["quote not found verbatim in the contract", "no quote", "no issue given",
                          "unknown kind 'risky'", "unknown party 'Bên B'"])


@unittest.skipUnless(tx.DEFAULT_JSON.exists(), "data/taxonomy/taxonomy.json not present")
class TaxonomyLens(unittest.TestCase):
    def test_every_risk_becomes_a_lookfor(self):
        t = tx.load()
        lens = from_taxonomy(t)
        self.assertEqual(len(lens), len(t.risks))
        self.assertEqual(len({l.id for l in lens}), len(lens))
        self.assertTrue(all(isinstance(l, LookFor) and l.affects in ("lessor", "lessee") for l in lens))
        b = next(l for l in lens if l.id == "taxonomy:B-DEP-04")
        self.assertEqual((b.affects, b.meta["group"]), ("lessee", "DEP"))


if __name__ == "__main__":
    unittest.main()
