"""Regression set: real Word templates in pipeline/data/real_docx (see its README)."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.data_paths import REAL_DOCX
from application.modules.ingestion import ingest as ing
from application.modules.ingestion.ingest import IngestError, ingest
from application.modules.ingestion.text import clean, norm

REAL = REAL_DOCX
FILES = sorted(REAL.glob("*.doc*")) if REAL.exists() else []
JUNK = "Doc1 - Copy (12) - Copy - Copy.docx"


def _squash(s: str) -> str:
    # compare content only: no whitespace, no table separators, bullets unified
    s = re.sub(r"(?m)^[•\-] ", "", norm(s).replace(" | ", " "))
    return "".join(s.replace("• ", "").replace("- ", "").split())


@unittest.skipUnless(FILES, "pipeline/data/real_docx not present")
class TestRealDocx(unittest.TestCase):
    def test_all_ingest(self):
        for f in FILES:
            with self.subTest(f.name):
                if f.name == JUNK:
                    with self.assertRaises(IngestError) as cm:
                        ingest(f)
                    self.assertEqual(cm.exception.reason, "no_text")
                    continue
                doc = ingest(f)
                self.assertGreater(len(doc.text), 3000)
                self.assertEqual(clean(doc.text), doc.text)
                self.assertFalse([w for w in doc.warnings if "LibreOffice" not in w], doc.warnings)

    def test_auto_numbering_found(self):
        expect = {"hop-dong-thue-nha-o_2810144434_2011152916_0804150405.docx": 23,
                  "mau-hop-dong-thue-nha-lam-van-phong-mau1.doc": 90,
                  "thue can ho chung cu.docx": 13}
        for name, n in expect.items():
            if ing._soffice() is None and name.endswith(".doc"):
                continue
            with self.subTest(name):
                self.assertEqual(ingest(REAL / name).raw["numbered_paragraphs"], n)

    @unittest.skipUnless(shutil.which("soffice"), "LibreOffice not installed")
    def test_matches_libreoffice_text_export(self):
        files = [f for f in FILES if f.name != JUNK]
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["soffice", f"-env:UserInstallation={Path(d, 'p').as_uri()}", "--headless",
                            "--convert-to", "txt:Text (encoded):UTF8", "--outdir", d]
                           + [str(f) for f in files], capture_output=True, timeout=600, check=True)
            for f in files:
                with self.subTest(f.name):
                    theirs = Path(d, f.stem + ".txt").read_text(encoding="utf-8-sig")
                    self.assertEqual(_squash(ingest(f).text), _squash(theirs))


if __name__ == "__main__":
    unittest.main()
