"""Build minimal .docx files in memory for tests."""
import io
import re
import zipfile
from xml.sax.saxutils import escape

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
      'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
      'xmlns:v="urn:schemas-microsoft-com:vml"')

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    '</Types>')
RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
    '</Relationships>')
DOC_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    '</Relationships>')


def t(s: str) -> str:
    return f'<w:r><w:t xml:space="preserve">{escape(s)}</w:t></w:r>'


def p(*runs: str, num: tuple[int, int] | None = None, style: str | None = None) -> str:
    ppr = ""
    if num or style:
        ppr = "<w:pPr>"
        if style:
            ppr += f'<w:pStyle w:val="{style}"/>'
        if num:
            ppr += f'<w:numPr><w:ilvl w:val="{num[1]}"/><w:numId w:val="{num[0]}"/></w:numPr>'
        ppr += "</w:pPr>"
    body = "".join(r if r.startswith("<") else t(r) for r in runs)
    return f"<w:p>{ppr}{body}</w:p>"


def lvl(ilvl: int, fmt: str, text: str, start: int = 1, extra: str = "") -> str:
    return (f'<w:lvl w:ilvl="{ilvl}"><w:start w:val="{start}"/><w:numFmt w:val="{fmt}"/>'
            f'<w:lvlText w:val="{escape(text, {chr(34): "&quot;"})}"/>{extra}</w:lvl>')


def numbering(abstracts: dict[int, list[str]], nums: dict[int, int | tuple[int, str]],
              extra_abstract: dict[int, str] | None = None) -> str:
    """abstracts: aid -> [lvl xml]; nums: numId -> aid or (aid, override xml)."""
    out = [f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:numbering {NS}>']
    for aid, lvls in abstracts.items():
        out.append(f'<w:abstractNum w:abstractNumId="{aid}">'
                   f'{(extra_abstract or {}).get(aid, "")}{"".join(lvls)}</w:abstractNum>')
    for nid, spec in nums.items():
        aid, ov = (spec, "") if isinstance(spec, int) else spec
        out.append(f'<w:num w:numId="{nid}"><w:abstractNumId w:val="{aid}"/>{ov}</w:num>')
    out.append("</w:numbering>")
    return "".join(out)


def styles(*style_xml: str) -> str:
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {NS}>'
            + "".join(style_xml) + "</w:styles>")


R_NS = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'


def field(instr: str, shown: str = "1") -> str:
    """Complex field run sequence (PAGE, NUMPAGES, ...)."""
    return ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            f'<w:r><w:instrText xml:space="preserve"> {instr} </w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            + t(shown) + '<w:r><w:fldChar w:fldCharType="end"/></w:r>')


def make_docx(body: str, numbering_xml: str | None = None, styles_xml: str | None = None,
              header: str | None = None, footer: str | None = None) -> bytes:
    """header/footer: paragraph XML for a default page header/footer."""
    refs, rels, types = "", DOC_RELS, CONTENT_TYPES
    parts = {}
    for kind, tag, xml in (("header", "hdr", header), ("footer", "ftr", footer)):
        if xml is None:
            continue
        rid = f"rId{kind}"
        parts[f"word/{kind}1.xml"] = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                                      f'<w:{tag} {NS} {R_NS}>{xml}</w:{tag}>')
        refs += f'<w:{kind}Reference w:type="default" r:id="{rid}"/>'
        rels = rels.replace("</Relationships>",
                            f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/'
                            f'officeDocument/2006/relationships/{kind}" Target="{kind}1.xml"/></Relationships>')
        types = types.replace("</Types>",
                              f'<Override PartName="/word/{kind}1.xml" ContentType="application/'
                              f'vnd.openxmlformats-officedocument.wordprocessingml.{kind}+xml"/></Types>')
    doc = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           f'<w:document {NS} {R_NS}><w:body>{body}<w:sectPr>{refs}</w:sectPr></w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/_rels/document.xml.rels", rels)
        z.writestr("word/document.xml", doc)
        z.writestr("word/numbering.xml", numbering_xml or numbering({}, {}))
        z.writestr("word/styles.xml", styles_xml or styles())
        for name, xml in parts.items():
            z.writestr(name, xml)
    return buf.getvalue()


RUNNING_HEADER = p("HỢP ĐỒNG THUÊ NHÀ Ở — Số: 15/2026/HĐTN")
RUNNING_FOOTER = p("Trang ", field("PAGE"), "/", field("NUMPAGES"))


def plain_docx(text: str, running: bool = True) -> bytes:
    """One paragraph per non-empty line of a clean contract; optional running header/footer."""
    body = "".join(p(line) for line in text.split("\n") if line)
    return make_docx(body, header=RUNNING_HEADER if running else None,
                     footer=RUNNING_FOOTER if running else None)


# --- auto-numbered twin of a plain-text contract ---

DIEU = re.compile(r"^Điều (\d+)\. (.*)$")
SUB = re.compile(r"^(\d+)\.(\d+)\. (.*)$")

TEMPLATE_NUMBERING = numbering(
    {1: [lvl(0, "decimal", "Điều %1.", extra='<w:suff w:val="space"/>'),
         lvl(1, "decimal", "%1.%2.", extra='<w:suff w:val="space"/>')]},
    {1: 1})


def numbered_twin(text: str) -> tuple[bytes, int]:
    """Rewrite `Điều N. ...` / `N.M. ...` lines of a clean contract as Word
    auto-numbered paragraphs (label removed from the text). Only lines whose
    numbers match what Word's counters would produce are converted, so the
    ingested text must equal the original exactly. Returns (docx, n_converted)."""
    paras, converted = [], 0
    top, sub = 0, 0
    for line in text.split("\n"):
        m, s = DIEU.match(line), SUB.match(line)
        if m and int(m.group(1)) == top + 1:
            top, sub = top + 1, 0
            paras.append(p(m.group(2), num=(1, 0)))
            converted += 1
        elif s and top and int(s.group(1)) == top and int(s.group(2)) == sub + 1:
            sub += 1
            paras.append(p(s.group(3), num=(1, 1)))
            converted += 1
        elif line:
            paras.append(p(line))
    return make_docx("".join(paras), TEMPLATE_NUMBERING), converted
