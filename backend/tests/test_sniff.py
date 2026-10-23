import io
import unittest
import zipfile
from pathlib import Path

from tests.data_paths import TEMPLATES
from application.modules.ingestion import ingest as ing
from application.modules.ingestion.ingest import IngestError, ingest, sniff

REPO = Path(__file__).resolve().parents[2]


def _zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, body in files.items():
            z.writestr(name, body)
    return buf.getvalue()


def _ole(*streams: str) -> bytes:
    # Header magic plus directory-entry names; enough for sniff().
    return ing._OLE + b"\x00" * 504 + b"".join(s.encode("utf-16-le") + b"\x00\x00" for s in streams)


class TestSniff(unittest.TestCase):
    def assertReason(self, data, reason):
        with self.assertRaises(IngestError) as cm:
            sniff(data)
        self.assertEqual(cm.exception.reason, reason)

    def test_empty(self):
        self.assertReason(b"", "empty")

    def test_pdf_with_leading_junk(self):
        self.assertEqual(sniff(b"%PDF-1.7\n..."), "pdf")
        self.assertEqual(sniff(b"\x00junk\n%PDF-1.4\n"), "pdf")

    def test_docx_minimal(self):
        self.assertEqual(sniff(_zip({"word/document.xml": b"<w:document/>"})), "docx")

    def test_other_zips_rejected(self):
        odt = _zip({"mimetype": b"application/vnd.oasis.opendocument.text", "content.xml": b""})
        self.assertReason(odt, "unsupported_type")
        self.assertReason(_zip({"xl/workbook.xml": b""}), "unsupported_type")
        self.assertReason(_zip({"a.txt": b"x"}), "unsupported_type")
        self.assertReason(b"PK\x03\x04garbage", "unsupported_type")

    def test_ole(self):
        self.assertEqual(sniff(_ole("Root Entry", "WordDocument", "1Table")), "doc")
        self.assertReason(_ole("Root Entry", "EncryptionInfo", "EncryptedPackage"), "encrypted")
        self.assertReason(_ole("Root Entry", "Workbook"), "unsupported_type")

    def test_images(self):
        self.assertEqual(sniff(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20), "png")
        self.assertEqual(sniff(b"\xff\xd8\xff\xe0" + b"\x00" * 20), "jpeg")
        self.assertEqual(sniff(b"II*\x00" + b"\x00" * 20), "tiff")
        self.assertEqual(sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 "), "webp")
        self.assertEqual(sniff(b"\x00\x00\x00\x18ftypheic\x00\x00"), "heic")

    def test_rtf_rejected(self):
        self.assertReason(b"{\\rtf1\\ansi ...}", "unsupported_type")

    def test_text_encodings(self):
        s = "Điều 1. Bên thuê phải đặt cọc 02 tháng tiền thuê.\n"
        self.assertEqual(sniff(s.encode("utf-8")), "txt")
        self.assertEqual(sniff(s.encode("utf-8-sig")), "txt")
        self.assertEqual(sniff(s.encode("utf-16")), "txt")        # with BOM
        self.assertEqual(sniff(s.encode("utf-16-le")), "txt")     # BOM-less
        self.assertEqual(sniff(s.encode("cp1258", "replace")), "txt")

    def test_binary_rejected(self):
        self.assertReason(bytes(range(256)) * 8, "unsupported_type")


class TestRealFiles(unittest.TestCase):
    CASES = {
        "pipeline/data/samples/thue_nha_o.docx": "docx",
        "pipeline/data/samples/thue_nha_o.txt": "txt",
        "pipeline/data/templates/9_hop-dong.txt": "txt",
        "RAW/Legal AI - PL - Note.pdf": "pdf",
        "pipeline/data/samples/plain.png": "png",
        "data/ocr_bench_photos/0_hop-dong_L1_0.jpg": "jpeg",
    }

    def test_real_files(self):
        for rel, kind in self.CASES.items():
            p = REPO / rel
            if not p.exists():
                continue
            with self.subTest(rel):
                self.assertEqual(sniff(p.read_bytes()), kind)

    def test_xlsx_rejected(self):
        p = REPO / "RAW" / "RD week 1 - Risk taxonomy.xlsx"
        if p.exists():
            with self.assertRaises(IngestError):
                sniff(p.read_bytes())


class TestIngestEntry(unittest.TestCase):
    def setUp(self):
        self._routes = dict(ing.ROUTES)
        ing.ROUTES["txt"] = lambda data, doc: setattr(doc, "text", "stub " * 100)

    def tearDown(self):
        ing.ROUTES.clear()
        ing.ROUTES.update(self._routes)

    def test_source_metadata(self):
        doc = ingest(b"Hello", filename="a.txt")
        self.assertEqual(doc.source["detected_type"], "txt")
        self.assertEqual(doc.source["size"], 5)
        self.assertEqual(len(doc.source["sha256"]), 64)
        self.assertEqual(doc.warnings, [])

    def test_extension_mismatch_warns(self):
        doc = ingest(b"Hello", filename="contract.pdf")
        self.assertEqual(len(doc.warnings), 1)
        self.assertIn("content is txt", doc.warnings[0])

    def test_unimplemented_route(self):
        with self.assertRaises(IngestError) as cm:
            ingest(b"\x00\x00\x00\x18ftypheic\x00\x00", filename="p.heic")
        self.assertEqual(cm.exception.reason, "not_implemented")
        self.assertIn("JPEG", cm.exception.message)

    def test_too_large(self):
        old = ing.MAX_BYTES
        ing.MAX_BYTES = 4
        try:
            with self.assertRaises(IngestError) as cm:
                ingest(b"Hello")
            self.assertEqual(cm.exception.reason, "too_large")
        finally:
            ing.MAX_BYTES = old

    def test_path_input(self):
        doc = ingest(TEMPLATES / "9_hop-dong.txt")
        self.assertEqual(doc.source["filename"], "9_hop-dong.txt")


if __name__ == "__main__":
    unittest.main()
