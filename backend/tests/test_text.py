import unicodedata
import unittest
from pathlib import Path

from tests.data_paths import TEMPLATES
from app.ingest.text import clean, find_span, norm

REPO = Path(__file__).resolve().parents[2]


class TestClean(unittest.TestCase):
    def test_nfc(self):
        decomposed = unicodedata.normalize("NFD", "Hợp đồng thuê nhà")
        self.assertNotEqual(decomposed, "Hợp đồng thuê nhà")
        self.assertEqual(clean(decomposed), "Hợp đồng thuê nhà")

    def test_newlines_unified(self):
        self.assertEqual(clean("a\r\nb\rc d\x0ce"), "a\nb\nc\nd\ne")

    def test_spaces_collapsed_within_lines_only(self):
        self.assertEqual(clean("  Điều\t1.  Đối  tượng  \n  2.1  x "),
                         "Điều 1. Đối tượng\n2.1 x")

    def test_blank_lines_capped_at_one(self):
        self.assertEqual(clean("\n\na\n\n\n\n b \n\n\n"), "a\n\nb")

    def test_invisibles_and_controls_removed(self):
        self.assertEqual(clean("﻿đặt​ cọc­\x00\x07"), "đặt cọc")

    def test_typography_kept(self):
        # clean is the document; quotes and dashes stay as written
        self.assertEqual(clean("“tiền cọc” – 2%"), "“tiền cọc” – 2%")

    def test_idempotent(self):
        s = " ﻿A\r\n\r\n\r\n\tB  C "
        self.assertEqual(clean(clean(s)), clean(s))


class TestNorm(unittest.TestCase):
    def test_all_whitespace_collapses(self):
        self.assertEqual(norm("Bên thuê\nphải  trả\n\ntiền"), "Bên thuê phải trả tiền")

    def test_typography_folded(self):
        self.assertEqual(norm("“cọc” ‘x’ a–b c—d e−f …"), "\"cọc\" 'x' a-b c-d e-f ...")

    def test_tone_placement_not_folded(self):
        # hoà (old style) vs hòa (new style) are different strings after NFC
        self.assertNotEqual(norm("hoà"), norm("hòa"))

    def test_d_lookalike_not_folded(self):
        self.assertNotEqual(norm("Điều"), norm("Ðiều"))

    def test_idempotent_and_consistent_with_clean(self):
        s = "“Điều 1”\r\n\r\n  tiền cọc – 2%…"
        self.assertEqual(norm(norm(s)), norm(s))
        self.assertEqual(norm(clean(s)), norm(s))

    def test_empty(self):
        self.assertEqual(norm(" \n\t "), "")


class TestFindSpan(unittest.TestCase):
    TEXT = clean("Điều 3. Đặt cọc\n3.1 Bên thuê phải đặt cọc\n“02 tháng” tiền thuê.\n"
                 "3.2 Tiền cọc – không hoàn trả.")

    def test_exact(self):
        s, e = find_span(self.TEXT, "Bên thuê phải đặt cọc")
        self.assertEqual(self.TEXT[s:e], "Bên thuê phải đặt cọc")

    def test_across_line_break_and_folded_quotes(self):
        s, e = find_span(self.TEXT, 'đặt cọc "02 tháng" tiền')
        self.assertEqual(self.TEXT[s:e], "đặt cọc\n“02 tháng” tiền")

    def test_offsets_point_at_original_typography(self):
        s, e = find_span(self.TEXT, "Tiền cọc - không")
        self.assertEqual(self.TEXT[s:e], "Tiền cọc – không")

    def test_drift_rejected(self):
        # the DEP-04 failure: model wrote "Bên cho thuê" where the contract says "Bên thuê"
        self.assertIsNone(find_span(self.TEXT, "Bên cho thuê phải đặt cọc"))

    def test_empty_span(self):
        self.assertIsNone(find_span(self.TEXT, "  \n"))

    def test_start_offset(self):
        first = find_span(self.TEXT, "cọc")
        second = find_span(self.TEXT, "cọc", first[1])
        self.assertGreater(second[0], first[0])
        self.assertEqual(self.TEXT[second[0]:second[1]], "cọc")

    def test_whole_text(self):
        self.assertEqual(find_span(self.TEXT, self.TEXT), (0, len(self.TEXT)))


class TestRealTemplates(unittest.TestCase):
    """Properties on the 100 collected templates (read-only shared data)."""

    def setUp(self):
        self.files = sorted(TEMPLATES.glob("*_hop-dong*.txt"))
        if not self.files:
            self.skipTest("pipeline/data/templates not present")

    def test_clean_idempotent_and_every_line_findable(self):
        for f in self.files:
            text = clean(f.read_text(encoding="utf-8"))
            self.assertEqual(clean(text), text, f.name)
            for line in text.split("\n"):
                if len(line) >= 20:
                    with self.subTest(doc=f.name, line=line[:40]):
                        self.assertIsNotNone(find_span(text, line))


if __name__ == "__main__":
    unittest.main()
