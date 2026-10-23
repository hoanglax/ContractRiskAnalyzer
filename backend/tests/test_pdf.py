import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from application.modules.ingestion import ingest as ing
from application.modules.ingestion.ingest import IngestError, ingest, strip_running_lines
from tests.docx_fixtures import RUNNING_FOOTER, RUNNING_HEADER, make_docx, p
from application.modules.ingestion.text import clean, find_span

REPO = Path(__file__).resolve().parents[2]
HAS_TOOLS = bool(shutil.which("pdftotext") and ing._soffice())

BODY = ("Điều 1. Đối tượng của hợp đồng. Bên cho thuê đồng ý cho Bên thuê thuê căn nhà "
        "tại địa chỉ ghi dưới đây, với diện tích sử dụng và trang thiết bị kèm theo. ")


class TestStripRunningLines(unittest.TestCase):
    WORDS = "nhà cọc thuê giá hạn điện nước phạt bàn giao sửa chữa".split()

    def pages(self, n):
        body = lambda i: [f"{self.WORDS[(i + k) % 11]} {self.WORDS[(i * k) % 11]} dòng {k}" for k in range(10)]
        return [["CÔNG TY ABC — HỢP ĐỒNG SỐ 12", *body(i), f"Trang {i}/{n}"] for i in range(1, n + 1)]

    def test_repeated_header_and_footer_removed(self):
        pages = self.pages(4)
        out, removed = strip_running_lines(pages)
        self.assertEqual(out[0], pages[0][1:-1])
        self.assertEqual(len(removed), 8)

    def test_identical_short_pages_survive(self):
        # a form repeated per tenant: short identical pages are content, not headers
        pages = [["Ông/Bà: ....", "CMND số: ....", "Địa chỉ: ...."] for _ in range(4)]
        out, removed = strip_running_lines(pages)
        self.assertEqual(out, pages)
        self.assertEqual(removed, [])

    def test_header_learned_on_long_pages_stripped_from_short_last_page(self):
        pages = self.pages(4)
        pages[-1] = ["CÔNG TY ABC — HỢP ĐỒNG SỐ 12", "BÊN A    BÊN B", "Trang 4/4"]
        out, _ = strip_running_lines(pages)
        self.assertEqual(out[-1], ["BÊN A    BÊN B"])

    def test_page_numbers_removed_even_without_repetition(self):
        for line in ("3", "- 3 -", "Trang 3", "Page 3 of 9", "trang 3 trên 9"):
            with self.subTest(line):
                out, _ = strip_running_lines([["nội dung", "khác", line]])
                self.assertEqual(out, [["nội dung", "khác"]])

    def test_content_is_not_removed(self):
        pages = [["Điều 1. Đối tượng", "x"], ["Điều 4. Giá thuê", "y"], ["Điều 7. Cam kết", "z"]]
        out, removed = strip_running_lines(pages)
        self.assertEqual(out, pages)            # digits masked, but the text differs
        self.assertEqual(removed, [])

    def test_only_peels_from_the_edge(self):
        # a repeated line deeper than EDGE_LINES inside a page is content, not a header
        pages = [[f"nội dung {w}" for w in self.WORDS[i:i + 4]] + ["HỢP ĐỒNG"]
                 + [f"kết {w}" for w in self.WORDS[i:i + 4]] for i in range(3)]
        out, _ = strip_running_lines(pages)
        self.assertIn("HỢP ĐỒNG", out[0])

    def test_single_page_keeps_repeated_text(self):
        out, removed = strip_running_lines([["CÔNG TY ABC", "nội dung", "kết"]])
        self.assertEqual(removed, [])


class TestRouteMocked(unittest.TestCase):
    """Route logic with pdftotext's output faked, OCR switched off
    (OCR of scanned pages is covered in test_ocr)."""

    def setUp(self):
        p = mock.patch.dict(ing.os.environ, {"OCR_ENGINE": "off"})
        p.start()
        self.addCleanup(p.stop)

    def run_pages(self, pages):
        with mock.patch.object(ing, "_pdftotext", return_value=pages), \
             mock.patch.object(ing, "_pdf_page_count", return_value=len(pages)):
            return ingest(b"%PDF-1.7 fake", filename="x.pdf")

    def test_broken_cid_page_dropped_with_warning(self):
        doc = self.run_pages([BODY * 3, "(cid:12)(cid:45)(cid:3)" * 30, BODY * 3])
        self.assertEqual([pg.chars > 0 for pg in doc.pages], [True, False, True])
        self.assertTrue(any("page 2: broken text layer" in w for w in doc.warnings))
        self.assertNotIn("cid", doc.text)

    def test_empty_middle_page_warns(self):
        doc = self.run_pages([BODY * 3, "", BODY * 3])
        self.assertTrue(any("page 2: no text layer" in w for w in doc.warnings))

    def test_short_last_page_is_normal(self):
        doc = self.run_pages([BODY * 3, BODY * 3, "BÊN CHO THUÊ          BÊN THUÊ\n(Ký, ghi rõ họ tên)"])
        self.assertFalse(any("OCR" in w for w in doc.warnings))

    def test_all_pages_empty_is_no_text(self):
        with self.assertRaises(IngestError) as cm:
            self.run_pages(["", " \n ", ""])
        self.assertEqual(cm.exception.reason, "no_text")

    def test_block_pages_and_offsets(self):
        doc = self.run_pages([BODY * 3, BODY * 2])
        self.assertEqual({b.page for b in doc.blocks}, {1, 2})
        for b in doc.blocks:
            self.assertEqual(doc.text[b.char_start:b.char_end], b.text)

    def test_misencoded_text_layer_warns(self):
        # real case: RAW/Legal AI_DE_week1.pdf ("Dàtà Enginêêr" for "Data Engineer")
        bad = ("Hợ p đồ ng chồ thuê nhà Dàtà Enginêêr pipêlinê mồdêl thêồ khồà Càồ "
               "Đà khà ồ sà t 9 nguồn dữ liệu và thu thập ") * 12
        doc = self.run_pages([bad])
        self.assertTrue(any("impossible as Vietnamese" in w for w in doc.warnings))

    def test_good_vietnamese_does_not_warn(self):
        doc = self.run_pages([BODY * 10])
        self.assertFalse(any("impossible" in w for w in doc.warnings))

    def test_missing_pdftotext(self):
        with mock.patch.object(ing.shutil, "which", return_value=None):
            with self.assertRaises(IngestError) as cm:
                ing._pdftotext(b"%PDF", True)
        self.assertEqual(cm.exception.reason, "conversion_failed")


@unittest.skipUnless(HAS_TOOLS, "pdftotext/LibreOffice not installed")
class TestRenderedTemplates(unittest.TestCase):
    """Text-layer PDFs rendered from templates, with a running header and a
    'Trang X/Y' footer that land in the middle of clauses."""

    @classmethod
    def setUpClass(cls):
        from tests.pdf_fixtures import render_pdfs, templates
        cls.pdfs = render_pdfs(templates(12))

    def test_span_survival(self):
        lines = found = windows = wfound = 0
        for name, (text, pdf) in self.pdfs.items():
            doc = ingest(pdf, filename=name.replace(".txt", ".pdf"))
            ls = [l for l in text.split("\n") if l]
            for l in ls:
                if len(l) >= 20 and set(l) - set(". "):      # dotted blanks wrap inside the dots
                    lines += 1
                    found += find_span(doc.text, l) is not None
            # quotes that cross a line (and so sometimes a page) boundary
            for a, b in zip(ls, ls[1:]):
                if len(a) >= 30 and len(b) >= 30:
                    windows += 1
                    wfound += find_span(doc.text, a[-30:] + " " + b[:30]) is not None
        self.assertGreaterEqual(found / lines, 0.995, f"{found}/{lines} lines")
        self.assertEqual(wfound, windows)

    def test_header_footer_removed_and_reported(self):
        for name, (text, pdf) in self.pdfs.items():
            doc = ingest(pdf, filename="x.pdf")
            with self.subTest(name):
                self.assertNotIn("15/2026/HĐTN", doc.text)
                self.assertNotRegex(doc.text, r"(?m)^Trang \d+/\d+$")
                self.assertTrue(any("running header/footer" in w for w in doc.warnings))
                self.assertFalse(any("OCR" in w for w in doc.warnings))
                self.assertEqual([pg.route for pg in doc.pages], ["native"] * len(doc.pages))

    def test_blank_page_in_the_middle(self):
        body = (p(BODY * 4) + p("<w:r><w:br w:type=\"page\"/></w:r>")
                + p("<w:r><w:br w:type=\"page\"/></w:r>") + p(BODY * 4))
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "b.docx"
            src.write_bytes(make_docx(body, header=RUNNING_HEADER, footer=RUNNING_FOOTER))
            pdf = ing.convert_with_soffice(src.read_bytes(), ".docx", "pdf")
        doc = ingest(pdf, filename="b.pdf")
        self.assertTrue(any("no text layer" in w or "only" in w for w in doc.warnings), doc.warnings)


@unittest.skipUnless(shutil.which("pdftotext"), "pdftotext not installed")
class TestRealPdfs(unittest.TestCase):
    def test_raw_pdfs(self):
        files = sorted((REPO / "RAW").glob("*.pdf"))
        if not files:
            self.skipTest("RAW/*.pdf not present")
        for f in files:
            with self.subTest(f.name):
                doc = ingest(f)
                self.assertGreater(len(doc.text), 1000)
                misencoded = any("impossible as Vietnamese" in w for w in doc.warnings)
                self.assertEqual(misencoded, f.name == "Legal AI_DE_week1.pdf")


if __name__ == "__main__":
    unittest.main()
