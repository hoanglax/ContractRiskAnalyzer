"""Text-layer PDFs from the templates, rendered by LibreOffice (batch, cached).

Cache lives in the system temp dir keyed by the fixture inputs, so repeated
test runs do not re-render. Nothing is written into the repo.
"""
import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

from tests.data_paths import TEMPLATES
from tests.docx_fixtures import plain_docx
from app.ingest.text import clean

REPO = Path(__file__).resolve().parents[2]
CACHE = Path(tempfile.gettempdir()) / "pipeline_pdf_fixtures"


def templates(limit: int | None = None) -> list[Path]:
    files = sorted(TEMPLATES.glob("*_hop-dong*.txt"),
                   key=lambda f: int(f.name.split("_")[0]))
    return files[:limit] if limit else files


def render_pdfs(files: list[Path], running: bool = True) -> dict[str, tuple[str, bytes]]:
    """{template name: (clean original text, pdf bytes)}; one soffice call for all misses."""
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    CACHE.mkdir(exist_ok=True)
    out, todo = {}, []
    for f in files:
        text = clean(f.read_text(encoding="utf-8"))
        docx = plain_docx(text, running)
        key = hashlib.sha256(docx).hexdigest()[:16]
        pdf = CACHE / f"{key}.pdf"
        out[f.name] = (text, pdf)
        if not pdf.exists():
            src = CACHE / f"{key}.docx"
            src.write_bytes(docx)
            todo.append(src)
    if todo:
        if exe is None:
            raise RuntimeError("LibreOffice not installed")
        with tempfile.TemporaryDirectory() as prof:
            for i in range(0, len(todo), 25):
                subprocess.run([exe, f"-env:UserInstallation={Path(prof).as_uri()}", "--headless",
                                "--convert-to", "pdf", "--outdir", str(CACHE)]
                               + [str(s) for s in todo[i:i + 25]],
                               capture_output=True, timeout=600, check=True)
        for s in todo:
            s.unlink(missing_ok=True)
    return {k: (text, pdf.read_bytes()) for k, (text, pdf) in out.items()}
