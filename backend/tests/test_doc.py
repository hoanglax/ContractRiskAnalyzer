import concurrent.futures
import unittest
from pathlib import Path
from unittest import mock

from tests.data_paths import TEMPLATES
from app.ingest import ingest as ing
from app.ingest.ingest import IngestError, convert_with_soffice, ingest
from tests.docx_fixtures import numbered_twin
from app.ingest.text import clean

REPO = Path(__file__).resolve().parents[2]
HAS_SOFFICE = ing._soffice() is not None


def _template(name="27_hop-dong.txt"):   # 25 auto-numberable headings
    return clean((TEMPLATES / name).read_text(encoding="utf-8"))


@unittest.skipUnless(HAS_SOFFICE, "LibreOffice not installed")
class TestDocRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A real .doc made by LibreOffice from an auto-numbered docx twin.
        cls.original = _template()
        twin, cls.n_numbered = numbered_twin(cls.original)
        cls.doc_bytes = convert_with_soffice(twin, ".docx", "doc")

    def test_is_real_doc(self):
        self.assertEqual(ing.sniff(self.doc_bytes), "doc")

    def test_text_and_numbering_survive(self):
        self.assertGreater(self.n_numbered, 0)
        doc = ingest(self.doc_bytes, filename="hd.doc")
        self.assertEqual(doc.text, "\n".join(l for l in self.original.split("\n") if l))
        self.assertEqual(doc.source["detected_type"], "doc")
        self.assertEqual(doc.raw["converted_from"], "doc")
        self.assertIn("LibreOffice", doc.warnings[0])
        self.assertEqual(doc.raw["numbered_paragraphs"], self.n_numbered)

    def test_concurrent_conversions(self):
        with concurrent.futures.ThreadPoolExecutor(3) as ex:
            texts = list(ex.map(lambda _: ingest(self.doc_bytes, filename="hd.doc").text, range(3)))
        self.assertEqual(len(set(texts)), 1)

    def test_garbage_doc_fails_cleanly(self):
        fake = ing._OLE + b"\x00" * 504 + "WordDocument".encode("utf-16-le") + b"\x00" * 2048
        # LibreOffice does not fail here: it imports the bytes as plain text.
        # The readability floor in ingest() is what stops it.
        with self.assertRaises(IngestError) as cm:
            ingest(fake, filename="bad.doc")
        self.assertEqual(cm.exception.reason, "no_text")
        self.assertIn("not readable", cm.exception.message)


class TestNoSoffice(unittest.TestCase):
    def test_missing_soffice(self):
        with mock.patch.object(ing, "_soffice", return_value=None):
            with self.assertRaises(IngestError) as cm:
                convert_with_soffice(b"x", ".doc", "docx")
        self.assertEqual(cm.exception.reason, "conversion_failed")
        self.assertIn("not installed", cm.exception.message)


if __name__ == "__main__":
    unittest.main()
