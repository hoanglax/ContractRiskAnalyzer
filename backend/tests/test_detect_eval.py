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
            "clause": None, "issue": "x", "affects": "lessee", "codes": ["B-DEP-02"], **kw}


DEPOSIT = "Bên A không hoàn trả tiền cọc trong mọi trường hợp."
RAISE = "Bên A được tăng giá thuê bất cứ lúc nào."
SUBLET = "Bên B được cho thuê lại nếu được Bên A đồng ý bằng văn bản."
GOLD = {"contract": "c.txt", "split": "dev", "exhaustive": True, "text_sha256": hashlib.sha256(TEXT.encode()).hexdigest(),
        "findings": [gold_item("P1", DEPOSIT), gold_item("N1", RAISE, origin="natural", codes=["B-DEP-05"]),
                     {"id": "P2", "origin": "planted", "kind": "missing", "quote": None, "char_start": None,
                      "char_end": None, "clause": None, "issue": "Không có điều khoản bàn giao", "affects": "both",
                      "codes": []}],
        "decoys": [{**gold_item("D1", SUBLET), "why_fair": "đúng luật"}]}


def pred(quote, kind="present", code="B-DEP-02"):
    if kind == "missing":
        return Finding(kind="missing", issue="thiếu", code=code)
    s, e = span_of(quote)
    return Finding(kind="present", issue="x", quote=quote, code=code, char_start=s, char_end=e)


LENS = [LookFor(id="B-DEP-02", title="Mất cọc", signs="giữ cọc", affects="lessee", meta={"group": "DEP"}),
        LookFor(id="B-DEP-05", title="Tăng giá", affects="lessee", meta={"group": "DEP"}),
        LookFor(id="B-TRM-06", title="Thiếu hiện trạng", affects="lessee", meta={"group": "TRM"})]


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
        self.assertEqual((len(r["dup"]), r["extra"]), (1, []))    # the duplicate is the same finding again

    def test_decoys_and_missing(self):
        r = score(GOLD, [pred(SUBLET), pred(RAISE), pred(None, "missing")])
        self.assertEqual(r["decoy_hits"], ["D1"])
        self.assertEqual(r["extra"], [])               # a decoy hit is not double-counted as extra
        self.assertEqual(r["strict"]["natural"], (1, 1))
        self.assertEqual([g["id"] for g in r["missing_gold"]], ["P2"])
        self.assertEqual(len(r["missing_pred"]), 1)

    def test_code_is_checked_on_matched_pairs(self):
        r = score(GOLD, [pred(DEPOSIT), pred(RAISE, code="B-DEP-02")])     # right span, wrong code for N1
        self.assertEqual(r["strict"]["all"], (2, 2))
        self.assertEqual(r["strict_code"]["all"], (1, 2))
        self.assertEqual((r["code_ok"], r["code_of"]["N1"]), ({"P1": True, "N1": False}, "B-DEP-02"))
        self.assertEqual(r["uncoded"], ["P2"])

    def test_right_code_is_matched_first_and_other_codes_are_dups(self):
        s, e = span_of(DEPOSIT)
        wrong = Finding(kind="present", issue="x", code="A-DEP-02", char_start=s, char_end=e)    # exact span
        right = Finding(kind="present", issue="x", code="B-DEP-02", char_start=s, char_end=e - 5)
        r = score(GOLD, [wrong, right])
        self.assertEqual((r["found"]["P1"], r["code_ok"]["P1"]), ("strict", True))
        self.assertEqual(([p.code for p in r["dup"]], r["extra"]), (["A-DEP-02"], []))


class Validate(unittest.TestCase):
    def test_good_gold(self):
        self.assertEqual(evalset.validate(GOLD, TEXT), [])

    def test_problems_are_reported(self):
        bad = json.loads(json.dumps(GOLD))
        bad["split"] = "train"
        bad["findings"][0]["char_start"] += 1                   # span no longer holds the quote
        bad["findings"][2]["quote"] = "x"                       # missing with a quote
        bad["decoys"][0]["id"] = "P1"                           # duplicate id
        bad["findings"][1]["codes"] = ["B-DEP-99"]              # not a taxonomy code
        del bad["findings"][2]["codes"]
        errs = evalset.validate(bad, TEXT + " ", codes={"B-DEP-02", "B-DEP-05"})   # text changed after labelling
        for needle in ("text_sha256", "split", "quote differs", "missing finding has no quote", "unique",
                       "not in the taxonomy: ['B-DEP-99']", "codes must be a list"):
            self.assertTrue(any(needle in e for e in errs), (needle, errs))


def reply(*findings):
    return LLMResult("```json\n" + json.dumps({"findings": list(findings)}, ensure_ascii=False) + "\n```",
                     "stop", {}, "p", "m")


class WholeDoc(unittest.TestCase):
    def setUp(self):
        with mock.patch.dict(os.environ, {"STRUCTURE_LLM": "off"}):
            self.doc = ingest(TEXT.encode(), "c.txt")

    def run_replies(self, replies, fn=whole_doc.detect, **kw):
        with mock.patch.object(whole_doc.llm, "chat", side_effect=list(replies)) as chat:
            return fn(self.doc, kw.pop("lens", LENS), **kw), chat

    def test_findings_are_parsed_grounded_and_bad_ones_sent_back(self):
        out, chat = self.run_replies([
            reply({"code": "B-DEP-02", "kind": "present", "quote": DEPOSIT, "issue": "mất cọc"},
                  {"code": "B-DEP-02", "kind": "present", "quote": "Bên A được giữ cọc", "issue": "bịa"},
                  {"code": "B-XXX-01", "kind": "missing", "quote": None, "issue": "mã bịa"},
                  {"code": "B-TRM-06", "kind": "missing", "quote": None, "issue": "thiếu hiện trạng"}),
            reply({"code": "B-DEP-05", "kind": "present", "quote": RAISE, "issue": "tăng giá"})])
        self.assertIsNone(out["error"])
        self.assertEqual([(f.code, f.kind) for f in out["kept"]],
                         [("B-DEP-02", "present"), ("B-TRM-06", "missing"), ("B-DEP-05", "present")])
        self.assertEqual((out["kept"][0].clause, out["kept"][0].affects), ("Điều 1", "lessee"))
        self.assertEqual((out["rejected"], out["warnings"], len(out["attempts"])), ([], [], 2))
        fix = chat.call_args_list[1].args[1]
        self.assertEqual([m["role"] for m in fix], ["user", "assistant", "user"])
        self.assertIn("trích dẫn không khớp nguyên văn", fix[2]["content"])
        self.assertIn("mã 'B-XXX-01' không có trong danh sách", fix[2]["content"])
        self.assertNotIn("mất cọc", fix[2]["content"])                    # kept findings are not sent back

    def test_still_rejected_after_retries_becomes_a_warning(self):
        bad = {"code": "B-DEP-02", "kind": "present", "quote": "Bên A được giữ cọc", "issue": "bịa"}
        out, chat = self.run_replies([reply(bad)] * 3)
        self.assertEqual(chat.call_count, 3)                             # first call + 2 retries
        self.assertEqual([w for _, w in out["rejected"]], ["quote not found verbatim in the contract"])
        self.assertEqual(len(out["warnings"]), 1)
        self.assertIsNone(out["error"])

    def test_unparseable_reply_is_retried_then_an_error(self):
        out, chat = self.run_replies([LLMResult("Tôi không thể trả lời.", "stop", {}, "p", "m")] * 3)
        self.assertIn("unparseable", out["error"])
        self.assertEqual((out["kept"], chat.call_count), ([], 3))
        out, _ = self.run_replies([LLMResult("Tôi không thể.", "stop", {}, "p", "m"), reply()])
        self.assertIsNone(out["error"])                                  # fixed by the retry

    def test_lens_and_temperature_reach_the_request(self):
        out, chat = self.run_replies([reply()], temperature=0.6)
        prompt = chat.call_args.args[1][0]["content"]
        self.assertIn("[B-DEP-02] Mất cọc: giữ cọc", prompt)
        self.assertEqual(chat.call_args.kwargs["sampling"]["temperature"], 0.6)
        self.assertEqual(out["kept"], [])

    def test_by_group_makes_one_call_per_group(self):
        out, chat = self.run_replies(
            [reply({"code": "B-DEP-02", "kind": "present", "quote": DEPOSIT, "issue": "mất cọc"}),
             LLMResult("hỏng", "length", {}, "p", "m"), LLMResult("hỏng", "length", {}, "p", "m"),
             LLMResult("hỏng", "length", {}, "p", "m")], fn=whole_doc.detect_by_group)
        prompts = [c.args[1][0]["content"] for c in chat.call_args_list]
        self.assertTrue("[B-DEP-05]" in prompts[0] and "[B-TRM-06]" not in prompts[0])
        self.assertIn("[B-TRM-06]", prompts[1])
        self.assertEqual([f.code for f in out["kept"]], ["B-DEP-02"])
        self.assertIsNone(out["error"])                                  # one broken group is a warning
        self.assertTrue(any("group TRM" in w for w in out["warnings"]))
        self.assertEqual([a["group"] for a in out["attempts"]], ["DEP", "TRM", "TRM", "TRM"])


if __name__ == "__main__":
    unittest.main()
