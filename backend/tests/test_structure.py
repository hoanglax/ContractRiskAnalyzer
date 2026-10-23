import unittest

from application.modules.ingestion.structure import segment
from application.modules.ingestion.text import clean


def seg(text):
    return segment(clean(text))


def labels(st):
    return [c.label for c in st.clauses]


class TierOne(unittest.TestCase):
    def test_plain_dieu_headings_and_offsets(self):
        t = clean("HỢP ĐỒNG\nBên A và bên B.\nĐiều 1. Đối tượng\nNội dung một.\nĐiều 2: Giá thuê\nNội dung hai.\nĐiều 3. Chấm dứt\nNội dung ba.")
        st, dg = segment(t)
        self.assertEqual(labels(st), ["Điều 1", "Điều 2", "Điều 3"])
        self.assertEqual(st.layout, "dieu_N")
        self.assertFalse(dg.needs_fallback)
        for c in st.clauses:                                   # offsets are in the text we passed
            self.assertTrue(t[c.char_start:].startswith("Điều"))
        self.assertEqual([c.char_end for c in st.clauses[:-1]], [c.char_start for c in st.clauses[1:]])
        self.assertEqual(st.clauses[-1].char_end, len(t))

    def test_cross_references_are_not_headings(self):
        t = ("Điều 1. Đối tượng\nNội dung.\nĐiều 2. Giá\nNội dung.\n"
             "Điều 6 của hợp đồng này được áp dụng.\nĐiều 3. Chấm dứt\nNội dung.\nĐiều 4, Điều 5 quy định thêm.\n")
        st, dg = seg(t)
        self.assertEqual(labels(st), ["Điều 1", "Điều 2", "Điều 3"])

    def test_standalone_marker_takes_title_from_next_line(self):
        st, _ = seg("ĐIỀU 1\nĐỐI TƯỢNG CỦA HỢP ĐỒNG\nNội dung.\nĐIỀU 2\nGIÁ THUÊ\nNội dung.\nĐIỀU 3\nCHẤM DỨT\nNội dung.")
        self.assertIn("ĐỐI TƯỢNG", st.clauses[0].heading)
        self.assertEqual(len(st.clauses), 3)

    def test_semicolon_delimiter_and_sentence_heading(self):
        long = "Bên thuê nhà phải trả tiền đầy đủ cho bên cho thuê nhà theo thỏa thuận " * 3
        st, _ = seg(f"ĐIỀU 1; ĐỐI TƯỢNG\nx\nĐiều 2: {long}\ny\nĐiều 3. Chấm dứt\nz")
        self.assertEqual(labels(st), ["Điều 1", "Điều 2", "Điều 3"])
        self.assertLessEqual(len(st.clauses[1].heading), 160)

    def test_roman_dieu(self):
        st, _ = seg("ĐIỀU I: QUY ĐỊNH CHUNG\na\nĐIỀU II: THANH TOÁN\nb\nĐIỀU III: CAM KẾT\nc")
        self.assertEqual(st.layout, "dieu_roman")
        self.assertEqual(len(st.clauses), 3)

    def test_dieu_beats_roman_party_blocks(self):
        t = "I. BÊN CHO THUÊ\nx\nII. BÊN THUÊ\ny\nIII. Thỏa thuận\nz\nĐiều 1. A\nq\nĐiều 2. B\nq\nĐiều 3. C\nq"
        st, _ = seg(t)
        self.assertEqual(st.layout, "dieu_N")

    def test_roman_layout_when_no_dieu(self):
        st, dg = seg("I. Đặc điểm nhà ở\na\nII. Giá cho thuê\nb\nIII. Thời hạn\nc\nIV. Quyền\nd")
        self.assertEqual(st.layout, "roman")
        self.assertEqual(len(st.clauses), 4)

    def test_numbered_needs_a_chain_not_list_noise(self):
        noise = "1. Bên A có quyền thu tiền thuê hàng tháng theo hợp đồng này và quy định;\n2. Bên B phải trả tiền;\n"
        st, _ = seg(noise * 3)
        self.assertEqual(st.clauses, [])                       # long / ';'-ending items are not headings
        st, _ = seg("1. Đối tượng\na\n2. Giá thuê\nb\n3. Thời hạn\nc\n4. Chấm dứt\nd")
        self.assertEqual(st.layout, "numbered")
        self.assertEqual(len(st.clauses), 4)

    def test_source_numbering_quirks_do_not_force_fallback(self):
        # repeated Điều 4 and a skipped 6: every heading is found, nothing hides in the gap
        t = "\n".join(f"Điều {n}. Mục {n}\ntext" for n in (1, 2, 3, 4, 4, 5, 7, 8))
        st, dg = seg(t)
        self.assertEqual(len(st.clauses), 8)
        self.assertEqual((dg.dups, dg.gaps), (1, 1))
        self.assertFalse(dg.needs_fallback)

    def test_gap_with_rejected_line_triggers_fallback(self):
        t = "Điều 1. A\nx\nĐiều 2. B\nx\nĐiều 3. C\nx\nĐiều 4 là điều khoản đặc biệt của bên A.\nĐiều 5. E\nx"
        st, dg = seg(t)
        self.assertEqual(labels(st), ["Điều 1", "Điều 2", "Điều 3", "Điều 5"])
        self.assertIn("gap_filled_by_rejected_line", dg.reasons)
        self.assertTrue(dg.needs_fallback)

    def test_unnumbered_titles_hand_over(self):
        st, dg = seg("HỢP ĐỒNG THUÊ PHÒNG\nBên A.\nTRÁCH NHIỆM CỦA CÁC BÊN\na\nTRÁCH NHIỆM CHUNG\nb")
        self.assertEqual(st.clauses, [])
        self.assertTrue(dg.needs_fallback)
        self.assertIn("no_marker_chain", dg.reasons)

    def test_điều_lệ_is_not_roman_L(self):
        st, _ = seg("Điều lệ công ty quy định rõ.\nĐiều 1. A\nx\nĐiều 2. B\nx\nĐiều 3. C\nx")
        self.assertEqual(len(st.clauses), 3)

    def test_empty_and_tiny(self):
        for t in ("", "Điều 1. Duy nhất"):
            st, dg = segment(t)
            self.assertEqual(st.clauses, [])
            self.assertTrue(dg.needs_fallback)


if __name__ == "__main__":
    unittest.main()
