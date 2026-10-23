"""Optional corpora for the ingest tests. Tests that need them skip when the folders are absent."""
import os
from pathlib import Path

DATA = Path(os.environ.get("INGEST_TEST_DATA", Path(__file__).resolve().parents[2] / "data" / "test"))

TEMPLATES = DATA / "templates"
REAL_DOCX = DATA / "real_docx"
SAMPLES = DATA / "samples"
