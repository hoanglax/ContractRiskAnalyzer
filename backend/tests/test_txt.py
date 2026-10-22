import unicodedata
import unittest
from pathlib import Path

from tests.data_paths import TEMPLATES
from app.ingest.ingest import IngestError, decode_text, ingest, legacy_encoding_warning
from app.ingest.text import clean, find_span

REPO = Path(__file__).resolve().parents[2]
VI = ("Điều 3. Đặt cọc\n3.1 Bên thuê phải đặt cọc cho Bên cho thuê số tiền tương đương "
      "02 tháng tiền thuê nhà ở. Tiền cọc được hoàn trả khi hết hạn hợp đồng, "
      "trừ trường hợp Bên thuê đơn phương chấm dứt hợp đồng trái pháp luật.\n") * 3


TONES = "̣̀́̃̉"


def _cp1258(s: str) -> bytes:
    """Encode the way Windows-1258 files store Vietnamese: base letter
    (with its shape mark: â ê ô ơ ư ă) precomposed, tone as a combining mark."""
    out = []
    for c in s:
        d = unicodedata.normalize("NFD", c)
        base = unicodedata.normalize("NFC", "".join(m for m in d if m not in TONES))
        out.append(base + "".join(m for m in d if m in TONES))
    return "".join(out).encode("cp1258")


class TestDecode(unittest.TestCase):
    def test_encodings_round_trip(self):
        for enc, expect in [("utf-8", "utf-8"), ("utf-8-sig", "utf-8-sig"), ("utf-16", "utf-16"),
                            ("utf-16-le", "utf-16-le"), ("utf-16-be", "utf-16-be")]:
            with self.subTest(enc):
                text, used, warnings = decode_text(VI.encode(enc))
                self.assertEqual(text, VI)
                self.assertEqual(used, expect)
                self.assertEqual(warnings, [])

    def test_cp1258_fallback(self):
        # cp1258 stores tones as combining marks after the base letter; clean()'s NFC recombines them.
        text, used, warnings = decode_text(_cp1258(VI))
        self.assertEqual(used, "cp1258")
        self.assertEqual(clean(text), clean(VI))
        self.assertEqual(len(warnings), 1)

    def test_undecodable_replaced_with_warning(self):
        # 0x81 is undefined in cp1258 and invalid as a UTF-8 start byte
        text, used, warnings = decode_text(b"abc \x81 def")
        self.assertEqual(used, "utf-8-replace")
        self.assertIn("�", text)
        self.assertEqual(len(warnings), 1)


class TestLegacyWarning(unittest.TestCase):
    def test_unicode_vietnamese_is_quiet(self):
        self.assertIsNone(legacy_encoding_warning(VI))

    def test_tcvn3(self):
        s = "Hîp ®ång thuª nhµ ë. Bªn thuª ph¶i ®Æt cäc cho Bªn cho thuª. " * 5
        self.assertIn("legacy Vietnamese font encoding", legacy_encoding_warning(s))

    def test_vni(self):
        s = "Hôïp ñoàng thueâ nhaø ôû. Beân thueâ phaûi ñaët coïc cho Beân cho thueâ. " * 5
        self.assertIn("legacy Vietnamese font encoding", legacy_encoding_warning(s))

    def test_double_encoded_utf8(self):
        # Windows-style: bytes undefined in cp1252 pass through as U+0081 etc.
        s = "".join(bytes([b]).decode("cp1252", "ignore") or chr(b) for b in VI.encode("utf-8"))
        self.assertIn("decoded as cp1252", legacy_encoding_warning(s))

    def test_few_symbols_are_quiet(self):
        self.assertIsNone(legacy_encoding_warning(VI + " Diện tích 20 m² · nhiệt độ 25° · ¾ · ¬"))


class TestRouteTxt(unittest.TestCase):
    def test_document_fields(self):
        doc = ingest(("﻿" + VI.replace("\n", "\r\n")).encode("utf-8"), filename="hd.txt")
        self.assertEqual(doc.text, clean(VI))
        self.assertEqual(doc.raw["encoding"], "utf-8-sig")
        self.assertEqual(doc.warnings, [])
        self.assertEqual([p.route for p in doc.pages], ["txt"])
        for b in doc.blocks:
            self.assertEqual(doc.text[b.char_start:b.char_end], b.text)
        self.assertEqual(len(doc.blocks), len([l for l in doc.text.split("\n") if l]))

    def test_legacy_warning_surfaces(self):
        s = "Hîp ®ång thuª nhµ ë. Bªn thuª ph¶i ®Æt cäc cho Bªn cho thuª. " * 10
        doc = ingest(s.encode("utf-8"), filename="tcvn3.txt")
        self.assertTrue(any("legacy" in w for w in doc.warnings))

    def test_too_short_is_no_text(self):
        with self.assertRaises(IngestError) as cm:
            ingest("Hợp đồng thuê nhà".encode("utf-8"), filename="short.txt")
        self.assertEqual(cm.exception.reason, "no_text")

    def test_unreadable_is_no_text(self):
        with self.assertRaises(IngestError) as cm:
            ingest(("Hợp đồng " + "#~|=" * 200).encode("utf-8"), filename="junk.txt")
        self.assertEqual(cm.exception.reason, "no_text")

    def test_real_templates(self):
        files = sorted(TEMPLATES.glob("*_hop-dong*.txt"))
        if not files:
            self.skipTest("pipeline/data/templates not present")
        for f in files:
            with self.subTest(f.name):
                doc = ingest(f)
                self.assertEqual(doc.text, clean(f.read_text(encoding="utf-8")))
                self.assertEqual([w for w in doc.warnings if not w.startswith("structure:")], [])   # text-integrity check; clause-map notes are separate

    def test_old_verified_spans_survive(self):
        """Every span the old pipeline verified is still found in Document.text."""
        import json
        caches = [p for p in (REPO / "data" / "demo" / "cache").glob("*.json")
                  if p.name != "_index.json"]
        if not caches:
            self.skipTest("demo cache not present")
        n = 0
        for p in caches:
            d = json.loads(p.read_text(encoding="utf-8"))
            doc = ingest(d["input"]["contract_text"].encode("utf-8"), filename=p.stem + ".txt")
            for r in d["verify"]["records"]:
                if r.get("verified"):
                    n += 1
                    with self.subTest(doc=p.stem, code=r["code"]):
                        self.assertIsNotNone(find_span(doc.text, r["span_exact"]))
        self.assertGreater(n, 0)


if __name__ == "__main__":
    unittest.main()
