import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.data_paths import SAMPLES, TEMPLATES
from app.ingest.ingest import IngestError, ingest
from app.ingest.text import clean, norm
from tests.docx_fixtures import (lvl, make_docx, numbered_twin, numbering, p, styles, t)

REPO = Path(__file__).resolve().parents[2]
PAD = p("Nội dung đệm để vượt ngưỡng tối thiểu của ingest. " * 8)   # MIN_CHARS


def text_of(body, numbering_xml=None, styles_xml=None):
    doc = ingest(make_docx(body + PAD, numbering_xml, styles_xml), filename="t.docx")
    return doc, doc.text.rsplit("\n", 1)[0]          # drop the padding line


class TestBody(unittest.TestCase):
    def test_paragraphs_breaks_tabs(self):
        _, s = text_of(p("Điều 1.", "<w:r><w:tab/></w:r>", "Đối tượng")
                       + p("dòng một", "<w:r><w:br/></w:r>", "dòng hai"))
        self.assertEqual(s, "Điều 1. Đối tượng\ndòng một\ndòng hai")

    def test_split_runs_join(self):
        _, s = text_of(p("Bên th", "uê phải ", "đặt cọc"))
        self.assertEqual(s, "Bên thuê phải đặt cọc")

    def test_special_chars(self):
        _, s = text_of(p("CMND", "<w:r><w:noBreakHyphen/></w:r>", "CCCD ",
                         '<w:r><w:sym w:font="Wingdings" w:char="F0A8"/></w:r>', " x"))
        self.assertEqual(s, "CMND-CCCD ¨ x")

    def test_tracked_changes_accepted(self):
        doc, s = text_of(p("Tiền cọc ",
                           '<w:del w:id="1"><w:r><w:delText>hai</w:delText></w:r></w:del>',
                           '<w:ins w:id="2">' + t("ba") + "</w:ins>", " tháng"))
        self.assertEqual(s, "Tiền cọc ba tháng")
        self.assertTrue(any("tracked changes" in w for w in doc.warnings))

    def test_hidden_text_dropped(self):
        doc, s = text_of(p("Hiển thị ", '<w:r><w:rPr><w:vanish/></w:rPr><w:t>ẩn</w:t></w:r>', "tiếp"))
        self.assertEqual(s, "Hiển thị tiếp")
        self.assertTrue(any("hidden" in w for w in doc.warnings))

    def test_fields_show_result_only(self):
        complex_field = ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
                         '<w:r><w:instrText> PAGE </w:instrText></w:r>'
                         '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
                         + t("3") + '<w:r><w:fldChar w:fldCharType="end"/></w:r>')
        simple = '<w:fldSimple w:instr=" DATE ">' + t("12/10/2026") + "</w:fldSimple>"
        _, s = text_of(p("Trang ", complex_field, " ngày ", simple))
        self.assertEqual(s, "Trang 3 ngày 12/10/2026")

    def test_hyperlink_and_content_control(self):
        _, s = text_of(p("Xem ", '<w:hyperlink r:id="x" xmlns:r="r">' + t("điều khoản") + "</w:hyperlink>")
                       + "<w:sdt><w:sdtContent>" + p("Trong content control") + "</w:sdtContent></w:sdt>")
        self.assertEqual(s, "Xem điều khoản\nTrong content control")

    def test_table_rows(self):
        tbl = ("<w:tbl>"
               "<w:tr><w:tc>" + p("BÊN A") + "</w:tc><w:tc>" + p("BÊN B") + "</w:tc></w:tr>"
               "<w:tr><w:tc>" + p("(Ký,") + p("ghi rõ họ tên)") + "</w:tc><w:tc>" + p("") + "</w:tc></w:tr>"
               "</w:tbl>")
        doc, s = text_of(p("Trước") + tbl + p("Sau"))
        self.assertEqual(s, "Trước\nBÊN A | BÊN B\n(Ký, ghi rõ họ tên)\nSau")
        self.assertEqual([b.kind for b in doc.blocks][:4], ["para", "table_row", "table_row", "para"])

    def test_nested_table_flattened_into_cell(self):
        inner = "<w:tbl><w:tr><w:tc>" + p("x") + "</w:tc><w:tc>" + p("y") + "</w:tc></w:tr></w:tbl>"
        _, s = text_of("<w:tbl><w:tr><w:tc>" + p("ngoài") + inner + "</w:tc><w:tc>" + p("z") + "</w:tc></w:tr></w:tbl>")
        self.assertEqual(s, "ngoài x | y | z")

    def test_textbox_once_after_anchor(self):
        box = ("<w:r><mc:AlternateContent><mc:Choice Requires=\"wps\"><w:drawing><wps:txbx><w:txbxContent>"
               + p("trong khung") + "</w:txbxContent></wps:txbx></w:drawing></mc:Choice>"
               "<mc:Fallback><w:pict><v:textbox><w:txbxContent>" + p("trong khung")
               + "</w:txbxContent></v:textbox></w:pict></mc:Fallback></mc:AlternateContent></w:r>")
        doc, s = text_of(p("neo ", box, "tiếp") + p("sau"))
        self.assertEqual(s, "neo tiếp\ntrong khung\nsau")
        self.assertTrue(any("text boxes" in w for w in doc.warnings))

    def test_blocks_offsets(self):
        doc, _ = text_of(p("một") + p("  hai  ba ") + p(""))
        for b in doc.blocks:
            self.assertEqual(doc.text[b.char_start:b.char_end], b.text)
        self.assertEqual(clean(doc.text), doc.text)

    def test_corrupt_docx(self):
        import io, zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("word/document.xml", "<w:document><unclosed>")
        with self.assertRaises(IngestError) as cm:
            ingest(buf.getvalue(), filename="bad.docx")
        self.assertEqual(cm.exception.reason, "unsupported_type")


class TestNumbering(unittest.TestCase):
    def test_dieu_and_sub_levels_restart(self):
        num = numbering({1: [lvl(0, "decimal", "Điều %1.", extra='<w:suff w:val="space"/>'),
                             lvl(1, "decimal", "%1.%2"),
                             lvl(2, "lowerLetter", "%3)")]}, {1: 1})
        body = (p("Đối tượng", num=(1, 0)) + p("Nhà ở", num=(1, 1)) + p("Diện tích", num=(1, 1))
                + p("Đặt cọc", num=(1, 0)) + p("Số tiền", num=(1, 1)) + p("tiền mặt", num=(1, 2))
                + p("chuyển khoản", num=(1, 2)) + p("Hoàn cọc", num=(1, 1)) + p("lãi", num=(1, 2)))
        _, s = text_of(body, num)
        self.assertEqual(s.split("\n"), [
            "Điều 1. Đối tượng", "1.1 Nhà ở", "1.2 Diện tích", "Điều 2. Đặt cọc", "2.1 Số tiền",
            "a) tiền mặt", "b) chuyển khoản", "2.2 Hoàn cọc", "a) lãi"])

    def test_formats(self):
        num = numbering({1: [lvl(0, "upperRoman", "ĐIỀU %1:"), lvl(1, "upperLetter", "%2."),
                             lvl(2, "decimalZero", "%3/"), lvl(3, "lowerRoman", "(%4)")]}, {1: 1})
        body = "".join(p("x", num=(1, 0)) for _ in range(4)) + p("y", num=(1, 1)) \
            + p("z", num=(1, 2)) + p("w", num=(1, 3)) + p("w", num=(1, 3))
        _, s = text_of(body, num)
        self.assertEqual(s.split("\n"), ["ĐIỀU I: x", "ĐIỀU II: x", "ĐIỀU III: x", "ĐIỀU IV: x",
                                         "A. y", "01/ z", "(i) w", "(ii) w"])

    def test_letters_past_z_repeat(self):
        num = numbering({1: [lvl(0, "lowerLetter", "%1)", start=26)]}, {1: 1})
        _, s = text_of(p("x", num=(1, 0)) + p("y", num=(1, 0)) + p("z", num=(1, 0)), num)
        self.assertEqual(s.split("\n"), ["z) x", "aa) y", "bb) z"])

    def test_two_lists_share_counter_unless_overridden(self):
        num = numbering({1: [lvl(0, "decimal", "%1.")]},
                        {1: 1, 2: 1,
                         3: (1, '<w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride>')})
        body = p("a", num=(1, 0)) + p("b", num=(1, 0)) + p("c", num=(2, 0)) + p("d", num=(3, 0))
        _, s = text_of(body, num)
        self.assertEqual(s.split("\n"), ["1. a", "2. b", "3. c", "1. d"])

    def test_numbering_through_style(self):
        num = numbering({1: [lvl(0, "decimal", "Điều %1.", extra='<w:pStyle w:val="Dieu"/>')]}, {5: 1})
        st = styles('<w:style w:type="paragraph" w:styleId="Dieu"><w:pPr><w:numPr><w:numId w:val="5"/>'
                    '</w:numPr></w:pPr></w:style>',
                    '<w:style w:type="paragraph" w:styleId="DieuDam"><w:basedOn w:val="Dieu"/></w:style>')
        _, s = text_of(p("Một", style="Dieu") + p("Hai", style="DieuDam"), num, st)
        self.assertEqual(s, "Điều 1. Một\nĐiều 2. Hai")

    def test_num_id_zero_turns_off_style_numbering(self):
        num = numbering({1: [lvl(0, "decimal", "%1.")]}, {5: 1})
        st = styles('<w:style w:type="paragraph" w:styleId="L"><w:pPr><w:numPr><w:numId w:val="5"/>'
                    '</w:numPr></w:pPr></w:style>')
        _, s = text_of(p("có số", style="L") + p("không số", style="L", num=(0, 0)), num, st)
        self.assertEqual(s, "1. có số\nkhông số")

    def test_legal_bullet_suffix(self):
        num = numbering({1: [lvl(0, "upperRoman", "%1."),
                             lvl(1, "decimal", "%1.%2", extra='<w:isLgl/><w:suff w:val="nothing"/>')],
                         2: [lvl(0, "bullet", "")]}, {1: 1, 2: 2})
        body = p("A", num=(1, 0)) + p("B", num=(1, 0)) + p("-x", num=(1, 1)) + p("ý", num=(2, 0))
        _, s = text_of(body, num)
        self.assertEqual(s.split("\n"), ["I. A", "II. B", "2.1-x", "• ý"])

    def test_unknown_format_warns(self):
        num = numbering({1: [lvl(0, "vietnameseCounting", "%1.")]}, {1: 1})
        doc, s = text_of(p("x", num=(1, 0)), num)
        self.assertEqual(s, "1. x")
        self.assertTrue(any("vietnameseCounting" in w for w in doc.warnings))

    def test_template_round_trip(self):
        """Auto-numbered twins of the 100 templates ingest back to the exact original text."""
        files = sorted(TEMPLATES.glob("*_hop-dong*.txt"))
        if not files:
            self.skipTest("pipeline/data/templates not present")
        total_docs = total_lines = 0
        for f in files:
            original = clean(f.read_text(encoding="utf-8"))
            data, n = numbered_twin(original)
            if not n:
                continue
            total_docs, total_lines = total_docs + 1, total_lines + n
            with self.subTest(f.name):
                doc = ingest(data, filename=f.stem + ".docx")
                # the twin has one paragraph per non-empty line, so blank lines disappear
                self.assertEqual(doc.text, "\n".join(l for l in original.split("\n") if l))
        self.assertGreater(total_docs, 20)
        print(f"\n  round-trip: {total_docs} templates, {total_lines} auto-numbered headings", end="")


@unittest.skipUnless(shutil.which("soffice"), "LibreOffice not installed")
class TestAgainstLibreOffice(unittest.TestCase):
    """LibreOffice renders numbering itself; our reconstruction must agree."""

    def test_numbering_matches_soffice(self):
        num = numbering({1: [lvl(0, "decimal", "Điều %1.", extra='<w:suff w:val="space"/>'),
                             lvl(1, "decimal", "%1.%2.", extra='<w:suff w:val="space"/>'),
                             lvl(2, "lowerLetter", "%3)", extra='<w:suff w:val="space"/>')],
                         2: [lvl(0, "upperRoman", "%1.", extra='<w:suff w:val="space"/>')]},
                        {1: 1, 2: 2,
                         3: (1, '<w:lvlOverride w:ilvl="0"><w:startOverride w:val="7"/></w:lvlOverride>')})
        body = (p("Đối tượng", num=(1, 0)) + p("Nhà", num=(1, 1)) + p("tầng", num=(1, 2))
                + p("phòng", num=(1, 2)) + p("Đất", num=(1, 1)) + p("Giá", num=(1, 0))
                + p("Một", num=(2, 0)) + p("Hai", num=(2, 0)) + p("Thời hạn", num=(1, 1))
                + p("Bảy", num=(3, 0)) + p("Tám", num=(3, 0)))
        data = make_docx(body, num)
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "n.docx"
            src.write_bytes(data)
            r = subprocess.run(["soffice", "--headless", "--convert-to", "txt:Text (encoded):UTF8",
                                "--outdir", d, str(src)], capture_output=True, timeout=120)
            out = Path(d) / "n.txt"
            if r.returncode or not out.exists():
                self.skipTest(f"soffice conversion failed: {r.stderr[:200]}")
            theirs = clean(out.read_text(encoding="utf-8-sig"))
        ours = ingest(make_docx(body + PAD, num), filename="n.docx").text.rsplit("\n", 1)[0]
        self.assertEqual(norm(ours), norm(theirs))


@unittest.skipUnless((SAMPLES / "thue_nha_o.docx").exists(), "sample docx missing")
class TestRealDocx(unittest.TestCase):
    def test_matches_txt_twin(self):
        doc = ingest(SAMPLES / "thue_nha_o.docx")
        twin = clean((SAMPLES / "thue_nha_o.txt").read_text(encoding="utf-8"))
        self.assertEqual(doc.warnings, [])
        # The twin glues w:br-separated lines and flattens the signature table;
        # compare with all whitespace and the table separator removed.
        squash = lambda s: "".join(norm(s).replace(" | ", "").split())
        self.assertEqual(squash(doc.text), squash(twin))


if __name__ == "__main__":
    unittest.main()
