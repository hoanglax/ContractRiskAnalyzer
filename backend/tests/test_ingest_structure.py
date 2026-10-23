import os
import unittest
from unittest import mock

from application.modules.ingestion import structure_llm as sl
from application.modules.ingestion.ingest import ingest
from application.adapters.llm import LLMResult

NUMBERED = ("HỢP ĐỒNG THUÊ NHÀ\nBên A cho Bên B thuê nhà theo các điều khoản sau đây, hai bên cùng thống nhất.\n"
            + "\n".join(f"Điều {n}. Mục số {n}\nNội dung của điều khoản số {n} được hai bên thỏa thuận cụ thể." for n in (1, 2, 3, 4)))
BODY = "Hai bên thực hiện đúng và đầy đủ các điều khoản đã ghi trong hợp đồng này, không bên nào được tự ý thay đổi. " * 6
TITLED = ("HỢP ĐỒNG THUÊ PHÒNG TRỌ\nBên A cho Bên B thuê phòng trọ theo các điều khoản sau đây, hai bên cùng thống nhất. " + BODY + "\n"
          "TRÁCH NHIỆM CỦA CÁC BÊN\n" + BODY + "\nTRÁCH NHIỆM CHUNG\n" + BODY)


class IngestStructure(unittest.TestCase):
    def test_numbered_contract_gets_a_clause_map(self):
        doc = ingest(NUMBERED.encode(), "a.txt")
        self.assertEqual(doc.structure.layout, "dieu_N")
        self.assertEqual([c.label for c in doc.structure.clauses], ["Điều 1", "Điều 2", "Điều 3", "Điều 4"])
        for c in doc.structure.clauses:
            self.assertTrue(doc.text[c.char_start:].startswith("Điều"))   # offsets are in doc.text
        self.assertEqual(doc.raw["structure"]["tier"], 1)

    def test_titled_contract_without_llm_has_empty_map_and_a_warning(self):
        with mock.patch.dict(os.environ, {"STRUCTURE_LLM": "off"}):
            doc = ingest(TITLED.encode(), "b.txt")
        self.assertEqual(doc.structure.clauses, [])
        self.assertTrue(any("LLM fallback is off" in w for w in doc.warnings))

    def test_titled_contract_with_llm_fallback(self):
        reply = LLMResult('{"headings": [{"lines": [2]}, {"lines": [4]}]}', "stop", {}, "fake", "m")
        with mock.patch.dict(os.environ, {"STRUCTURE_LLM": "auto"}), \
             mock.patch.object(sl.llm, "chat", return_value=reply), mock.patch.object(sl, "CACHE", sl.CACHE / "test-ingest"), \
             mock.patch.object(sl, "_cache_key", side_effect=lambda t, m: sl.CACHE / "never-exists.json"):
            doc = ingest(TITLED.encode(), "b.txt")
        self.assertEqual([c.heading for c in doc.structure.clauses], ["TRÁCH NHIỆM CỦA CÁC BÊN", "TRÁCH NHIỆM CHUNG"])
        self.assertEqual(doc.raw["structure"]["tier"], 2)

    def test_a_crashing_segmenter_does_not_break_ingest(self):
        with mock.patch("application.modules.ingestion.structure.segment", side_effect=RuntimeError("boom")):
            doc = ingest(NUMBERED.encode(), "a.txt")
        self.assertEqual(doc.structure.clauses, [])
        self.assertTrue(any("clause map failed" in w for w in doc.warnings))
        self.assertIn("Điều 1", doc.text)


if __name__ == "__main__":
    unittest.main()
