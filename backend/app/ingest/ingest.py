"""Ingest: one file in, one Document out (INGEST_PLAN.md).

Every downstream stage works on `Document.text` only; this is the only module
that knows about file formats. The type is decided from the file's bytes, not
its name — uploads get renamed. A mismatching extension is a warning.

Routes are added step by step (INGEST_PLAN.md §8); a recognised type whose
route does not exist yet raises IngestError("not_implemented").
"""
import hashlib
import io
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from app.ingest import vlm
from app.ingest.text import clean, implausible_words, readable_ratio

MAX_BYTES = 50 * 1024 * 1024

# What each kind is normally called; used only to warn on a misleading name.
EXTENSIONS = {
    "txt": {".txt", ".text", ".md", ""},
    "docx": {".docx", ".docm", ".dotx", ".dotm"},
    "doc": {".doc", ".dot"},
    "pdf": {".pdf"},
    "png": {".png"},
    "jpeg": {".jpg", ".jpeg", ".jpe", ".jfif"},
    "tiff": {".tif", ".tiff"},
    "webp": {".webp"},
    "heic": {".heic", ".heif"},
}
IMAGE_KINDS = {"png", "jpeg", "tiff", "webp", "heic"}


class IngestError(Exception):
    """File cannot become text. `reason` is a stable code, the message is for humans.

    Codes: empty, too_large, unsupported_type, encrypted, not_implemented,
    no_text, conversion_failed.
    """

    def __init__(self, reason: str, message: str):
        super().__init__(f"{reason}: {message}")
        self.reason = reason
        self.message = message


@dataclass
class Block:
    kind: str                  # para | table_row | qr
    text: str
    char_start: int
    char_end: int
    page: int | None = None


@dataclass
class Page:
    n: int
    route: str                 # txt | docx | native | tesseract | vision
    chars: int
    quality: float | None = None


@dataclass
class Clause:
    label: str                 # "Điều 5"
    heading: str
    char_start: int
    char_end: int
    level: int = 1


@dataclass
class Structure:
    layout: str = "freeform"   # dieu_N | dieu_roman | roman | numbered | titled | freeform (no clauses found)
    clauses: list[Clause] = field(default_factory=list)


@dataclass
class Document:
    text: str                  # clean() text; the gate checks spans against this
    source: dict               # filename, sha256, size, detected_type
    blocks: list[Block] = field(default_factory=list)
    pages: list[Page] = field(default_factory=list)
    structure: Structure = field(default_factory=Structure)
    warnings: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


# ---------------- type detection ----------------

_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _utf16_name(s: str) -> bytes:
    return s.encode("utf-16-le")


def _sniff_zip(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = set(z.namelist())
            mimetype = z.read("mimetype").decode("ascii", "replace").strip() \
                if "mimetype" in names else ""
    except zipfile.BadZipFile:
        raise IngestError("unsupported_type", "file looks like a ZIP archive but is corrupt") from None
    if "word/document.xml" in names:
        return "docx"
    if mimetype == "application/vnd.oasis.opendocument.text":
        raise IngestError("unsupported_type",
                          "OpenDocument text (.odt) is not supported; save it as .docx")
    if "xl/workbook.xml" in names or "ppt/presentation.xml" in names:
        raise IngestError("unsupported_type", "spreadsheets and presentations are not contracts")
    raise IngestError("unsupported_type", "ZIP archive that is not a Word document")


def _sniff_ole(data: bytes) -> str:
    # Compound File directory entries hold stream names in UTF-16LE.
    if _utf16_name("EncryptedPackage") in data:
        raise IngestError("encrypted", "the document is password-protected; remove the password and retry")
    if _utf16_name("WordDocument") in data:
        return "doc"
    raise IngestError("unsupported_type", "legacy Office file that is not a Word document")


def _looks_like_text(data: bytes) -> bool:
    head = data[:65536]
    if head.startswith((b"\xff\xfe", b"\xfe\xff", b"\xef\xbb\xbf")):
        return True
    if b"\x00" in head:
        # BOM-less UTF-16: NULs on every other byte for Latin-script text.
        even, odd = head[0::2].count(0), head[1::2].count(0)
        half = len(head) / 2
        return max(even, odd) > 0.3 * half and min(even, odd) < 0.05 * half
    controls = sum(b < 32 and b not in b"\t\n\r\x0c" for b in head)
    return controls <= 0.01 * len(head)


def sniff(data: bytes) -> str:
    """Return the file kind from its bytes, or raise IngestError."""
    if not data:
        raise IngestError("empty", "the file is empty")
    if b"%PDF-" in data[:1024]:          # spec allows junk before the header
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        return _sniff_zip(data)
    if data.startswith(_OLE):
        return _sniff_ole(data)
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith((b"II*\x00", b"MM\x00*")):
        return "tiff"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"mif1", b"msf1", b"heim", b"heis"):
        return "heic"
    if data.lstrip()[:5] == b"{\\rtf":
        raise IngestError("unsupported_type", "RTF is not supported; save it as .docx")
    if _looks_like_text(data):
        return "txt"
    raise IngestError("unsupported_type", "unrecognised binary file")


# ---------------- shared helpers ----------------

MIN_CHARS = 300      # less than this after ingest = nothing to analyse
MIN_READABLE = 0.5   # readable_ratio floor; real pages >= 0.935, byte garbage ~0.01
MAX_IMPLAUSIBLE = 0.04   # implausible_words share; real texts <= 0.016, mis-encoded PDF 0.086
MIN_STRUCTURE_CHARS = 1500   # below this, a missing clause map is not worth a warning
MIN_MARKED_WORDS = 50    # too few Vietnamese words -> the ratio is noise


def line_blocks(text: str, kind: str = "para", page: int | None = None,
                offset: int = 0) -> list[Block]:
    """One Block per non-empty line of clean `text`; offsets shifted by `offset`."""
    blocks, pos = [], 0
    for line in text.split("\n"):
        if line:
            blocks.append(Block(kind, line, offset + pos, offset + pos + len(line), page))
        pos += len(line) + 1
    return blocks


# ---------------- txt ----------------

# Latin-1 letters that are in the Vietnamese alphabet. Any other Latin-1
# character in bulk means the bytes were never Unicode Vietnamese: TCVN3
# (.VnTime: "Hîp ®ång"), VNI ("Hôïp ñoàng"), or UTF-8 read as cp1252 ("Há»£p").
_VI_LATIN1 = set("ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝàáâãèéêìíòóôõùúý")
_LEGIT_SYMBOLS = set(" °×±²³µ")


def _foreign_latin1(s: str) -> int:
    return sum(" " <= c <= "ÿ" and c not in _VI_LATIN1 and c not in _LEGIT_SYMBOLS
               for c in s)


def _cp1252_bytes(s: str) -> bytes:
    """Inverse of Windows' cp1252 decode, which passes the 5 undefined bytes
    (0x81 0x8D 0x8F 0x90 0x9D) through as U+0081 etc. Unencodable chars dropped."""
    out = bytearray()
    for c in s:
        try:
            out += c.encode("cp1252")
        except UnicodeEncodeError:
            if ord(c) < 256:
                out.append(ord(c))
    return bytes(out)


def legacy_encoding_warning(s: str) -> str | None:
    """Heuristic: warn when the text looks like a legacy Vietnamese encoding
    or double-encoded UTF-8. Detection only; nothing is converted."""
    non_ascii = sum(ord(c) > 127 for c in s)
    foreign = _foreign_latin1(s)
    if foreign < 20 or foreign < 0.15 * non_ascii:
        return None
    # Only used to pick the message, never as the text. Double-encoded UTF-8
    # re-decodes almost cleanly; TCVN3/VNI bytes are mostly invalid UTF-8.
    repaired = _cp1252_bytes(s).decode("utf-8", "replace")
    if repaired.count("�") < foreign / 10 and _foreign_latin1(repaired) < foreign / 4:
        return ("text looks like UTF-8 that was decoded as cp1252 and saved again "
                "(e.g. 'Há»£p' for 'Hợp'); re-save the file as UTF-8")
    return ("text looks like a legacy Vietnamese font encoding (TCVN3/.VnTime or VNI, "
            "e.g. 'Hîp ®ång' for 'Hợp đồng'); convert it to Unicode before analysis")


def decode_text(data: bytes) -> tuple[str, str, list[str]]:
    """Bytes -> (str, encoding, warnings).

    Order: BOM (utf-8-sig / utf-16) -> BOM-less UTF-16 -> strict UTF-8 ->
    cp1258 -> UTF-8 with replacement (warned)."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", "replace"), "utf-8-sig", []
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", "replace"), "utf-16", []
    head = data[:65536]
    if b"\x00" in head:
        # Latin-script UTF-16: NUL is the high byte -> odd index for LE, even for BE.
        enc = "utf-16-le" if head[1::2].count(0) > head[0::2].count(0) else "utf-16-be"
        return data.decode(enc, "replace"), enc, []
    try:
        return data.decode("utf-8"), "utf-8", []
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp1258"), "cp1258", ["file is not UTF-8; decoded as Windows-1258 (cp1258)"]
    except UnicodeDecodeError:
        pass
    return (data.decode("utf-8", "replace"), "utf-8-replace",
            ["file is not valid UTF-8 or cp1258; undecodable bytes were replaced with U+FFFD"])


def route_txt(data: bytes, doc: Document) -> None:
    raw, enc, warnings = decode_text(data)
    doc.warnings.extend(warnings)
    if enc != "utf-8-replace" and "�" in raw:
        doc.warnings.append(f"text contains {raw.count(chr(0xfffd))} replacement characters (U+FFFD)")
    legacy = legacy_encoding_warning(raw)       # before clean(): it drops U+00AD, TCVN3's 'ư'
    if legacy:
        doc.warnings.append(legacy)
    doc.text = clean(raw)
    doc.blocks = line_blocks(doc.text, page=1)
    doc.pages = [Page(1, "txt", len(doc.text))]
    doc.raw = {"encoding": enc}


# ---------------- docx ----------------

def route_docx(data: bytes, doc: Document) -> None:
    from app.ingest import docx_text
    try:
        lines, warnings, raw = docx_text.extract(data)
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        raise IngestError("unsupported_type", f"corrupt Word document ({e})") from None
    doc.warnings.extend(warnings)
    pos, parts = 0, []
    for ln in lines:
        text = clean(ln.text)
        if not text:
            continue
        doc.blocks.append(Block(ln.kind, text, pos, pos + len(text), None))
        parts.append(text)
        pos += len(text) + 1
    doc.text = "\n".join(parts)
    doc.pages = [Page(1, "docx", len(doc.text))]   # docx has no fixed pages
    doc.raw = raw


# ---------------- doc (legacy Word, via LibreOffice) ----------------

SOFFICE_TIMEOUT = 120


def _soffice() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def convert_with_soffice(data: bytes, src_ext: str, target: str) -> bytes:
    """Convert a file with headless LibreOffice and return the output bytes.

    Each call gets its own throwaway user profile: concurrent soffice processes
    sharing the default profile block or fail silently."""
    exe = _soffice()
    if exe is None:
        raise IngestError("conversion_failed",
                          "LibreOffice (soffice) is required to read this file type but is not installed")
    with tempfile.TemporaryDirectory(prefix="ingest_") as d:
        src = Path(d) / f"in{src_ext}"
        src.write_bytes(data)
        cmd = [exe, f"-env:UserInstallation={Path(d, 'profile').as_uri()}", "--headless",
               "--norestore", "--convert-to", target, "--outdir", str(Path(d, "out")), str(src)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=SOFFICE_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise IngestError("conversion_failed",
                              f"LibreOffice did not finish within {SOFFICE_TIMEOUT}s") from None
        outs = list(Path(d, "out").glob("in.*"))
        if r.returncode != 0 or not outs:
            detail = (r.stderr or r.stdout).strip()[:300] or f"exit code {r.returncode}"
            raise IngestError("conversion_failed", f"LibreOffice could not convert the file ({detail})")
        return outs[0].read_bytes()


def route_doc(data: bytes, doc: Document) -> None:
    docx = convert_with_soffice(data, ".doc", "docx")
    route_docx(docx, doc)
    doc.warnings.insert(0, "legacy .doc converted to .docx by LibreOffice before extraction")
    doc.raw["converted_from"] = "doc"


# ---------------- pdf (text layer) ----------------

PDF_MIN_PAGE_CHARS = 200     # below this a page is probably a scan (INGEST_PLAN.md §4 pdf)
PDF_MIN_LAST_PAGE_CHARS = 1  # the last page is often just the signature block (18/100 rendered
                             # templates end on a 16-180 char page); only an empty one counts
# pdftotext -layout. Measured on 100 rendered templates: default mode treats a
# line-final "-" as hyphenation and glues lines ("QĐ-UB" -> "QĐUB",
# "---o0o---" + title); -layout does not. Lines found 99.4% vs 99.2%.
PDF_LAYOUT = True
EDGE_LINES = 3               # how many lines at the top/bottom of a page can be header/footer
REPEAT_SHARE = 0.6           # a line at the same edge position on >= 60% of pages repeats

_PAGE_NO = re.compile(r"^(?:-\s*)?(?:(?:trang|page)\s*)?\d{1,4}(?:\s*(?:/|of|trên)\s*\d{1,4})?(?:\s*-)?$", re.I)


def _pdftotext(data: bytes, layout: bool) -> list[str]:
    exe = shutil.which("pdftotext")
    if exe is None:
        raise IngestError("conversion_failed", "pdftotext (poppler-utils) is required for PDF input")
    cmd = [exe, "-enc", "UTF-8"] + (["-layout"] if layout else []) + ["-", "-"]
    try:
        r = subprocess.run(cmd, input=data, capture_output=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise IngestError("conversion_failed", "pdftotext did not finish within 120s") from None
    err = r.stderr.decode("utf-8", "replace")
    if r.returncode != 0:
        if "password" in err.lower() or "encrypt" in err.lower():
            raise IngestError("encrypted", "the PDF is password-protected; remove the password and retry")
        raise IngestError("conversion_failed", f"pdftotext failed ({err.strip()[:300]})")
    pages = r.stdout.decode("utf-8", "replace").split("\f")
    if pages and not pages[-1].strip():
        pages.pop()                                  # pdftotext ends every page with \f
    return pages


def _edge_key(line: str) -> str:
    """Compare header/footer candidates with digits masked ("Trang 3/7" ~ "Trang 4/7")."""
    return re.sub(r"\d+", "#", line)


def strip_running_lines(pages: list[list[str]]) -> tuple[list[list[str]], list[str]]:
    """Remove running headers/footers and page numbers from per-page line lists.

    A line is removed when it sits within EDGE_LINES of the top or bottom of
    its page and either (a) the same text (digits masked) appears at the same
    edge position on >= REPEAT_SHARE of pages, or (b) it is a bare page number
    ("3", "- 3 -", "Trang 3/7", "Page 3 of 7"). Returns (pages, removed lines).

    A repeated line must also occur on at least one *long* page (one with a
    header, a body and a footer: > 2 * EDGE_LINES lines). On short pages every
    line is "at the edge", so identical short pages (a form repeated per
    tenant) would otherwise be stripped whole."""
    n = len(pages)
    counts: dict[tuple[str, int, str], int] = {}
    on_long: set[tuple[str, int, str]] = set()
    for lines in pages:
        nonempty = [i for i, l in enumerate(lines) if l]
        is_long = len(nonempty) > 2 * EDGE_LINES
        for side, idxs in (("top", nonempty[:EDGE_LINES]), ("bottom", nonempty[::-1][:EDGE_LINES])):
            for pos, i in enumerate(idxs):
                k = (side, pos, _edge_key(lines[i]))
                counts[k] = counts.get(k, 0) + 1
                if is_long:
                    on_long.add(k)
    repeated = {k for k, c in counts.items() if k in on_long and c >= max(2, REPEAT_SHARE * n)}

    out, removed = [], []
    for lines in pages:
        nonempty = [i for i, l in enumerate(lines) if l]
        drop = set()
        for side, idxs in (("top", nonempty[:EDGE_LINES]), ("bottom", nonempty[::-1][:EDGE_LINES])):
            for pos, i in enumerate(idxs):
                if (side, pos, _edge_key(lines[i])) in repeated or _PAGE_NO.match(lines[i]):
                    drop.add(i)
                else:
                    break           # only peel from the edge inwards
        removed.extend(lines[i] for i in sorted(drop))
        out.append([l for i, l in enumerate(lines) if i not in drop])
    return out, removed


PDF_OCR_DPI = 150


def _render_page(data: bytes, n: int) -> bytes:
    """Page n (1-based) of a PDF as PNG bytes."""
    exe = shutil.which("pdftoppm")
    if exe is None:
        raise vlm.VlmError("pdftoppm (poppler-utils) is required to OCR PDF pages")
    with tempfile.TemporaryDirectory(prefix="ingest_") as d:
        src = Path(d, "in.pdf")
        src.write_bytes(data)
        cmd = [exe, "-png", "-r", str(PDF_OCR_DPI), "-f", str(n), "-l", str(n),
               "-singlefile", str(src), str(Path(d, "page"))]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=120)
        except subprocess.TimeoutExpired:
            raise vlm.VlmError(f"rendering page {n} timed out") from None
        out = Path(d, "page.png")
        if r.returncode != 0 or not out.exists():
            raise vlm.VlmError(f"could not render page {n}")
        return out.read_bytes()


def _pdf_page_count(data: bytes) -> int | None:
    exe = shutil.which("pdfinfo")
    if exe is None:
        return None
    r = subprocess.run([exe, "-"], input=data, capture_output=True, timeout=60)
    m = re.search(rb"^Pages:\s+(\d+)", r.stdout, re.M)
    return int(m.group(1)) if m else None


def route_pdf(data: bytes, doc: Document) -> None:
    raw_pages = _pdftotext(data, PDF_LAYOUT)
    n_pages = _pdf_page_count(data) or len(raw_pages)
    raw_pages += [""] * (n_pages - len(raw_pages))     # pdftotext drops trailing empty pages
    if not raw_pages:
        raise IngestError("no_text", "the PDF has no pages")

    # 1. find pages without a usable text layer
    texts, quality, bad = [], [], []
    for n, p in enumerate(raw_pages, 1):
        text = clean(p)
        q = readable_ratio(text)
        if "(cid:" in text or (text and q < MIN_READABLE):
            bad.append((n, "broken text layer (unreadable characters)"))
            text = ""
        elif len(text) < (PDF_MIN_LAST_PAGE_CHARS if n == len(raw_pages) else PDF_MIN_PAGE_CHARS):
            bad.append((n, f"only {len(text)} characters" if text else "no text layer"))
        texts.append(text)
        quality.append(round(q, 3) if text else None)
    routes = ["native"] * len(raw_pages)

    # 2. OCR the pages without a usable text layer, if an engine is configured
    ocr_info = {}
    use_ocr = bool(bad) and vlm.engine() == "vlm"
    ocr_done = []
    for n, why in bad:
        if not use_ocr:
            doc.warnings.append(f"page {n}: {why}; it looks scanned and needs OCR (OCR is not available)")
            continue
        try:
            ocr_text, info = vlm.transcribe(_render_page(data, n), "image/png")
        except vlm.VlmError as e:
            doc.warnings.append(f"page {n}: {why}; OCR failed ({e})")
            continue
        ocr_text = clean(ocr_text)
        if not ocr_text:
            doc.warnings.append(f"page {n}: {why}; OCR found no text")
            continue
        texts[n - 1], routes[n - 1] = ocr_text, "vision"
        quality[n - 1] = round(readable_ratio(ocr_text), 3)
        ocr_done.append(n)
        ocr_info = {"model": info["model"]}
    if ocr_done:
        doc.warnings.append(f"pages {', '.join(map(str, ocr_done))} were read by a vision model "
                            f"({ocr_info['model']}); check them against the original")

    # 3. strip running headers/footers across all pages, native and OCR'd alike
    page_lines, removed = strip_running_lines([t.split("\n") for t in texts])

    pos, parts = 0, []
    for n, lines in enumerate(page_lines, 1):
        text = "\n".join(l for l in lines if l)
        doc.pages.append(Page(n, routes[n - 1], len(text), quality[n - 1]))
        if not text:
            continue
        doc.blocks.extend(line_blocks(text, page=n, offset=pos))
        parts.append(text)
        pos += len(text) + 1
    doc.text = "\n".join(parts)

    if removed:
        uniq = sorted({_edge_key(l) for l in removed})
        doc.warnings.append(f"removed {len(removed)} running header/footer/page-number lines: "
                            + "; ".join(repr(u) for u in uniq[:8]) + (" …" if len(uniq) > 8 else ""))
    doc.raw = {"pdf_pages": len(raw_pages), "layout_mode": PDF_LAYOUT,
               "removed_lines": removed, "low_text_pages": [n for n, _ in bad], "ocr": ocr_info}


# ---------------- images (vision model) ----------------

IMAGE_MIME = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}


def route_image(data: bytes, doc: Document) -> None:
    kind = doc.source["detected_type"]
    if vlm.engine() != "vlm":
        raise IngestError("not_implemented",
                          "image input needs OCR; set OCR_API_KEY and OCR_MODEL (see ingest/vlm.py)")
    try:
        raw, info = vlm.transcribe(data, IMAGE_MIME[kind])
    except vlm.VlmError as e:
        raise IngestError("conversion_failed", str(e)) from None
    doc.text = clean(raw)
    doc.blocks = line_blocks(doc.text, page=1)
    doc.pages = [Page(1, "vision", len(doc.text), round(readable_ratio(doc.text), 3))]
    doc.warnings.append(f"text was read from the image by a vision model ({info['model']}); "
                        "check it against the original")
    doc.raw = {"model": info["model"], "usage": info["usage"]}


# ---------------- entry point ----------------

ROUTES = {   # kind -> fn(data: bytes, doc: Document) -> None
    "txt": route_txt,
    "docx": route_docx,
    "doc": route_doc,
    "pdf": route_pdf,
    **dict.fromkeys(IMAGE_MIME, route_image),
}


def ingest(src: str | Path | bytes, filename: str | None = None) -> Document:
    """Turn a file (path or bytes) into a Document. Raises IngestError."""
    if isinstance(src, (str, Path)):
        path = Path(src)
        filename = filename or path.name
        if path.stat().st_size > MAX_BYTES:
            raise IngestError("too_large", f"file is over {MAX_BYTES // 2**20} MB")
        data = path.read_bytes()
    else:
        data = bytes(src)
    if len(data) > MAX_BYTES:
        raise IngestError("too_large", f"file is over {MAX_BYTES // 2**20} MB")

    kind = sniff(data)
    doc = Document(text="", source={"filename": filename, "sha256": hashlib.sha256(data).hexdigest(),
                                    "size": len(data), "detected_type": kind})
    if filename:
        ext = Path(filename).suffix.lower()
        if ext not in EXTENSIONS[kind]:
            doc.warnings.append(f"file is named '{filename}' but its content is {kind}")

    route = ROUTES.get(kind)
    if route is None:
        hint = "; convert the photo to JPEG or PNG" if kind == "heic" else ""
        raise IngestError("not_implemented", f"{kind} input is not supported yet{hint}")
    route(data, doc)
    if len(doc.text) < MIN_CHARS:
        raise IngestError("no_text", f"only {len(doc.text)} characters of text after ingest "
                                     f"(minimum {MIN_CHARS})")
    ratio = readable_ratio(doc.text)
    if ratio < MIN_READABLE:
        raise IngestError("no_text", f"extracted text is not readable: only {ratio:.0%} letters/digits "
                                     f"(minimum {MIN_READABLE:.0%}); the file is probably corrupt")
    bad, marked = implausible_words(doc.text)
    if marked >= MIN_MARKED_WORDS and len(bad) > MAX_IMPLAUSIBLE * marked:
        doc.warnings.append(
            f"{len(bad)}/{marked} words ({len(bad) / marked:.0%}) are impossible as Vietnamese "
            f"(e.g. {', '.join(repr(w) for w in bad[:4])}); the text layer is probably mis-encoded "
            f"and quotes may not match the visible document")
    add_structure(doc)
    return doc


def structure_llm_enabled() -> bool:
    return os.environ.get("STRUCTURE_LLM", "auto") != "off"


def add_structure(doc: Document) -> None:
    """Fill doc.structure (clause map). Never raises: a failure costs the clause map, not the document."""
    try:
        from app.ingest.structure import segment
        from app.ingest.structure_llm import segment_auto
        if structure_llm_enabled():
            doc.structure, dg, warns = segment_auto(doc.text)
        else:
            doc.structure, dg = segment(doc.text)
            warns = [f"structure: tier-1 not confident ({', '.join(dg.reasons)}); LLM fallback is off"] if dg.needs_fallback else []
        if len(doc.text) >= MIN_STRUCTURE_CHARS:           # a short note or form is not expected to have a clause map
            doc.warnings.extend(warns)
        doc.raw["structure"] = {"layout": dg.layout, "n_headings": dg.n_headings, "numbers": dg.numbers,
                                "dups": dg.dups, "gaps": dg.gaps, "resets": dg.resets, "reasons": dg.reasons,
                                "tier": 2 if "tier2" in dg.reasons else 1}
    except Exception as e:                                  # noqa: BLE001 - see docstring
        doc.structure = Structure()
        doc.warnings.append(f"structure: clause map failed ({type(e).__name__}: {e})")
