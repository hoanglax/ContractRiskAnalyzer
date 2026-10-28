import re
import unittest

from application.modules.legal_retrieval import kb
from application.modules.taxonomy import taxonomy as tx
from tests.data_paths import DATA

HEADER = ["", "", "Mã", "Tên", "Mức độ", "Dấu hiệu nhận biết", "Căn cứ pháp lý", "Rủi ro thực tế", "Nhãn"]
SHEETS = {
    "Quy ước": [[], ["", "", "QUY ƯỚC"], ["", "", "Mức độ rủi ro:"],
                ["", "", "            1. LOW:"], ["", "", "   Thủ tục"], ["", "", "            2. MEDIUM:"], ["", "", "Mập mờ"],
                ["", "", "            3. HIGH:"], ["", "", "Thiệt hại"], ["", "", "            4. CRITICAL:"], ["", "", "Tổn thất"]],
    "1": [[], ["", "", "2, NHÓM ĐẶT CỌC & THỎA THUẬN TIỀN THUÊ (DEPOSIT & PAYMENT)"], [], HEADER,
          ["", "", "A - DEP - 01", "Cọc trái pháp luật", "CRITICAL", "Cọc bảo đảm nghĩa vụ trái luật",
           "Điều 117, 123, 328 BLDS 2015", "Vô hiệu\nMất tiền", "DAT_COC, NGHIA_VU"],
          [],
          ["", "", "B-DEP-08", "Tiền thuê không rõ", "MEDUIUM", "Không rõ giá thuê",
           "Điều 398 BLDS 2015, Điều 14 Bộ luật Kinh doanh bất động sản 2023\nLuật Nhà ở 2013\nĐiều 280/283 BLDS 2015,",
           "Tranh chấp", "PAYMENT \nCLARITY"]],
}

# cited articles the workbook gets wrong, reported to whoever edits it; remove each once the workbook is fixed
KNOWN_MISSING = ["A-MNT-02: luat_kdbds_2023 Điều 132"]   # KDBĐS 2023 ends at Điều 83; Luật Nhà ở 2023 Điều 132 fits


class Build(unittest.TestCase):
    def setUp(self):
        self.t = tx.build(SHEETS)
        self.by = {r["code"]: r for r in self.t["risks"]}

    def test_scale_and_group(self):
        self.assertEqual(self.t["severity_scale"], {"LOW": "Thủ tục", "MEDIUM": "Mập mờ", "HIGH": "Thiệt hại",
                                                    "CRITICAL": "Tổn thất"})
        self.assertEqual(self.t["groups"], [{"n": 2, "name": "ĐẶT CỌC & THỎA THUẬN TIỀN THUÊ",
                                             "name_en": "DEPOSIT & PAYMENT", "code": "DEP"}])

    def test_codes_normalised_and_fields_split(self):
        self.assertEqual(list(self.by), ["A-DEP-01", "B-DEP-08"])
        a = self.by["A-DEP-01"]
        self.assertEqual((a["party"], a["group"], a["severity"]), ("A", "DEP", "CRITICAL"))
        self.assertEqual(a["consequences"], ["Vô hiệu", "Mất tiền"])
        self.assertEqual(a["labels"], ["DAT_COC", "NGHIA_VU"])
        self.assertEqual(a["citations"], [{"law": "blds_2015", "dieu": [117, 123, 328], "text": "Điều 117, 123, 328 BLDS 2015"}])

    def test_corrections_and_unknowns_are_issues(self):
        b = self.by["B-DEP-08"]
        self.assertEqual(b["severity"], "MEDIUM")
        self.assertEqual([(c["law"], c["dieu"]) for c in b["citations"]],
                         [("blds_2015", [398]), ("luat_kdbds_2023", [14]), (None, []), ("blds_2015", [280, 283])])
        self.assertEqual(b["labels"], ["PAYMENT", "CLARITY"])
        self.assertEqual(len(self.t["issues"]), 3)
        self.assertTrue(all(i.startswith("B-DEP-08: ") for i in self.t["issues"]))

    def test_unreadable_severity_is_an_error(self):
        bad = {"1": SHEETS["1"][:4] + [["", "", "A-DEP-01", "x", "SEVERE"]]}
        with self.assertRaises(ValueError):
            tx.build(bad)

    def test_duplicate_code_is_an_error(self):
        row = ["", "", "A-DEP-01", "x", "LOW"]
        with self.assertRaises(ValueError):
            tx.build({"1": SHEETS["1"][:4] + [row, row]})


@unittest.skipUnless(tx.DEFAULT_XLSX.exists(), "data/Risk Taxonomy.xlsx not present")
class RealWorkbook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.built = tx.build(tx.read_xlsx(tx.DEFAULT_XLSX))

    def test_committed_json_is_current(self):
        """data/taxonomy/taxonomy.json is regenerated from the workbook (python -m application.modules.taxonomy.taxonomy build)."""
        self.assertEqual(tx.DEFAULT_JSON.read_text(encoding="utf-8"), tx.dumps(self.built))

    def test_load(self):
        t = tx.load()
        self.assertEqual(len(t.risks), len(self.built["risks"]))
        self.assertEqual({g["code"] for g in t.groups}, {r.group for r in t.risks})
        self.assertTrue(all(r.severity in tx.SEVERITIES for r in t.risks))
        self.assertEqual(t.by_code["B-DEP-04"].party, "B")

    @unittest.skipUnless((DATA / "kb").exists(), "data/test/kb not present")
    def test_cited_articles_exist(self):
        files = {f.stem: f for d in kb.DEFAULT_CORPUS for f in d.glob("*.txt")}
        missing = []
        for r in self.built["risks"]:
            for c in r["citations"]:
                if c["law"] is None:
                    continue
                text = files[c["law"]].read_text(encoding="utf-8")
                missing += [f"{r['code']}: {c['law']} Điều {n}" for n in c["dieu"]
                            if not re.search(rf"^\s*Điều {n}\.", text, re.M)]
        self.assertEqual(missing, KNOWN_MISSING)


if __name__ == "__main__":
    unittest.main()
