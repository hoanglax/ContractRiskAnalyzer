import hashlib
import json
import os
import unittest
from unittest import mock

from application.modules.detection import evalset, whole_doc
from application.modules.detection.finding import Finding, LookFor
from application.modules.detection.score import jaccard, score
from application.modules.ingestion.ingest import ingest
from application.adapters.llm import LLMResult

TEXT = """HỢP ĐỒNG THUÊ PHÒNG
Điều 1. Tiền cọc
Bên B đặt cọc 2 tháng tiền thuê. Bên A không hoàn trả tiền cọc trong mọi trường hợp.
Điều 2. Cho thuê lại
Bên B được cho thuê lại nếu được Bên A đồng ý bằng văn bản.
Điều 3. Giá thuê
Bên A được tăng giá thuê bất cứ lúc nào. Giá thuê là 3.000.000 đồng/tháng, trả trước ngày 05 hằng tháng.
Điều 4. Điều khoản chung
Hai bên cam kết thực hiện đúng các điều khoản trên; hợp đồng lập thành 02 bản, mỗi bên giữ 01 bản."""


def span_of(quote):
    s = TEXT.index(quote)
    return s, s + len(quote)


def gold_item(id_, quote, origin="planted", **kw):
    s, e = span_of(quote)
    return {"id": id_, "origin": origin, "kind": "present", "quote": quote, "char_start": s, "char_end": e,
            "clause": None, "issue": "x", "affects": "lessee", **kw}


DEPOSIT = "Bên A không hoàn trả tiền cọc trong mọi trường hợp."
RAISE = "Bên A được tăng giá thuê bất cứ lúc nào."
SUBLET = "Bên B được cho thuê lại nếu được Bên A đồng ý bằng văn bản."
GOLD = {"contract": "c.txt", "split": "dev", "exhaustive": True, "text_sha256": hashlib.sha256(TEXT.encode()).hexdigest(),
        "findings": [gold_item("P1", DEPOSIT), gold_item("N1", RAISE, origin="natural"),
                     {"id": "P2", "origin": "planted", "kind": "missing", "quote": None, "char_start": None,
                      "char_end": None, "clause": None, "issue": "Không có điều khoản bàn giao", "affects": "both"}],
        "decoys": [{**gold_item("D1", SUBLET), "why_fair": "đúng luật"}]}


def pred(quote, kind="present"):
    if kind == "missing":
        return Finding(kind="missing", issue="thiếu")
    s, e = span_of(quote)
    return Finding(kind="present", issue="x", quote=quote, char_start=s, char_end=e)


class Scoring(unittest.TestCase):
    def test_jaccard(self):
        self.assertEqual(jaccard((0, 10), (0, 10)), 1.0)
        self.assertEqual(jaccard((0, 10), (5, 15)), 5 / 15)
        self.assertEqual(jaccard((0, 5), (5, 10)), 0.0)

    def test_strict_needs_half_overlap_loose_any(self):
        s, e = span_of(DEPOSIT)
        wide = Finding(kind="present", issue="x", char_start=s, char_end=e + 80)     # Jaccard 51/131 < 0.5
        r = score(GOLD, [wide])
        self.assertEqual(r["found"]["P1"], "loose")
        self.assertEqual((r["strict"]["planted"], r["loose"]["planted"]), ((0, 1), (1, 1)))

    def test_one_prediction_matches_one_gold(self):
        r = score(GOLD, [pred(DEPOSIT), pred(DEPOSIT)])
        self.assertEqual(r["strict"]["planted"], (1, 1))
        self.assertEqual(len(r["extra"]), 1)          # the duplicate is an extra

    def test_decoys_and_missing(self):
        r = score(GOLD, [pred(SUBLET), pred(RAISE), pred(None, "missing")])
        self.assertEqual(r["decoy_hits"], ["D1"])
        self.assertEqual(r["extra"], [])               # a decoy hit is not double-counted as extra
        self.assertEqual(r["strict"]["natural"], (1, 1))
        self.assertEqual([g["id"] for g in r["missing_gold"]], ["P2"])
        self.assertEqual(len(r["missing_pred"]), 1)


class Validate(unittest.TestCase):
    def test_good_gold(self):
        self.assertEqual(evalset.validate(GOLD, TEXT), [])

    def test_problems_are_reported(self):
        bad = json.loads(json.dumps(GOLD))
        bad["split"] = "train"
        bad["findings"][0]["char_start"] += 1                   # span no longer holds the quote
        bad["findings"][2]["quote"] = "x"                       # missing with a quote
        bad["decoys"][0]["id"] = "P1"                           # duplicate id
        errs = evalset.validate(bad, TEXT + " ")                # text changed after labelling
        for needle in ("text_sha256", "split", "quote differs", "missing finding has no quote", "unique"):
            self.assertTrue(any(needle in e for e in errs), (needle, errs))


class WholeDoc(unittest.TestCase):
    def setUp(self):
        with mock.patch.dict(os.environ, {"STRUCTURE_LLM": "off"}):
            self.doc = ingest(TEXT.encode(), "c.txt")

    def run_reply(self, reply, lens=None, **kw):
        with mock.patch.object(whole_doc.llm, "chat", return_value=LLMResult(reply, "stop", {}, "p", "m")) as chat:
            return whole_doc.detect(self.doc, lens, **kw), chat

    def test_findings_are_parsed_and_grounded(self):
        reply = "```json\n" + json.dumps({"findings": [
            {"kind": "present", "quote": DEPOSIT, "issue": "mất cọc", "affects": "lessee"},
            {"kind": "present", "quote": "Bên A được giữ cọc", "issue": "bịa", "affects": "lessee"},
            {"kind": "missing", "quote": None, "issue": "thiếu bàn giao", "affects": "both"}]}, ensure_ascii=False) + "\n```"
        out, _ = self.run_reply(reply)
        self.assertIsNone(out["error"])
        self.assertEqual([f.kind for f in out["kept"]], ["present", "missing"])
        self.assertEqual(out["kept"][0].clause, "Điều 1")
        self.assertEqual([w for _, w in out["rejected"]], ["quote not found verbatim in the contract"])

    def test_unparseable_reply_is_an_error_not_an_exception(self):
        out, _ = self.run_reply("Tôi không thể trả lời.")
        self.assertIn("unparseable", out["error"])
        self.assertEqual(out["kept"], [])

    def test_lens_and_temperature_reach_the_request(self):
        out, chat = self.run_reply('{"findings": []}', lens=[LookFor(id="x:1", title="Mất cọc", signs="giữ cọc")],
                                   temperature=0.6)
        prompt = chat.call_args.args[1][0]["content"]
        self.assertIn("[x:1] Mất cọc: giữ cọc", prompt)
        self.assertEqual(chat.call_args.kwargs["sampling"]["temperature"], 0.6)
        self.assertEqual(out["kept"], [])


if __name__ == "__main__":
    unittest.main()
