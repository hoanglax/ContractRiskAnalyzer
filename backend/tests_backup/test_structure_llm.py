import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import llm
from app.ingest import structure_llm as sl
from app.llm import LLMError, LLMResult
from app.ingest.text import clean

TITLED = clean("HỢP ĐỒNG THUÊ PHÒNG\nBên A cho thuê.\nTRÁCH NHIỆM CỦA CÁC BÊN\nBên A lo điện.\nTRÁCH NHIỆM CHUNG\nHai bên thực hiện.")
NUMBERED = clean("\n".join(f"Điều {n}. Mục {n}\nnội dung" for n in (1, 2, 3, 4)))


def fake(text, finish="stop"):
    calls = []

    def ask(task, messages, **kw):
        calls.append(task)
        return LLMResult(text, finish, {}, "fake", "fake-model")
    ask.calls = calls
    return ask


class Answer(unittest.TestCase):
    L = ["a", "b", "", "d", "e"]

    def test_valid(self):
        self.assertEqual(sl.parse_answer('{"headings": [{"lines": [0]}, {"lines": [3, 4]}]}', self.L), [(0, None), (3, 4)])
        self.assertEqual(sl.parse_answer('x {"headings": []} y', self.L), [])      # prose around the JSON is tolerated
        self.assertEqual(sl.parse_answer("[]", self.L), [])                       # the model's own "no headings"
        self.assertEqual(sl.parse_answer('[{"lines": [0]}, {"lines": [3]}]', self.L), [(0, None), (3, None)])

    def test_rejections(self):
        for bad in ("no json here", '{"headings": [{"lines": [9]}]}', '{"headings": [{"lines": [2]}]}',   # out of range, blank
                    '{"headings": [{"lines": [3]}, {"lines": [1]}]}',                                      # not increasing
                    '{"headings": [{"lines": [0, 3]}]}', '{"headings": [{"lines": ["0"]}]}', '{"headings": 5}'):
            self.assertIsInstance(sl.parse_answer(bad, self.L), str, bad)


class Tier2(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        p = mock.patch.object(sl, "CACHE", Path(self.tmp.name))
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_titled_document_gets_clauses_with_offsets(self):
        st, warns = sl.segment_llm(TITLED, fake('{"headings": [{"lines": [2]}, {"lines": [4]}]}'))
        self.assertEqual([c.heading for c in st.clauses], ["TRÁCH NHIỆM CỦA CÁC BÊN", "TRÁCH NHIỆM CHUNG"])
        self.assertEqual(st.layout, "titled")
        self.assertTrue(TITLED[st.clauses[1].char_start:].startswith("TRÁCH NHIỆM CHUNG"))
        self.assertEqual(st.clauses[-1].char_end, len(TITLED))

    def test_bad_answers_fall_back_to_nothing(self):
        for ans, fin in (("garbage", "stop"), ('{"headings": [{"lines": [99]}]}', "stop"),
                         ('{"headings": [{"lines": [2]}]}', "stop"),                       # only 1 heading
                         ('{"headings": [{"lines": [2]}, {"lines": [4]}]}', "length")):    # truncated by the server
            st, warns = sl.segment_llm(TITLED, fake(ans, fin), use_cache=False)
            self.assertIsNone(st)
            self.assertTrue(warns)

    def test_server_down_keeps_tier1(self):
        def down(*a, **k):
            raise LLMError("connection refused")
        st, dg, warns = sl.segment_auto(TITLED, down)
        self.assertEqual(st.clauses, [])
        self.assertTrue(any("unavailable" in w for w in warns))

    def test_confident_tier1_never_calls_the_model(self):
        ask = fake("{}")
        st, dg, warns = sl.segment_auto(NUMBERED, ask)
        self.assertEqual(len(st.clauses), 4)
        self.assertEqual(ask.calls, [])

    def test_cache_hit_skips_the_model(self):
        ask = fake('{"headings": [{"lines": [2]}, {"lines": [4]}]}')
        sl.segment_auto(TITLED, ask)
        sl.segment_auto(TITLED, ask)
        self.assertEqual(len(ask.calls), 1)

    def test_segment_auto_uses_tier2_when_tier1_has_nothing(self):
        st, dg, warns = sl.segment_auto(TITLED, fake('{"headings": [{"lines": [2]}, {"lines": [4]}]}'))
        self.assertEqual(len(st.clauses), 2)
        self.assertIn("tier2", dg.reasons)


class Config(unittest.TestCase):
    def test_remote_profile_is_refused_without_allow_remote(self):
        cfg = {"default_profile": "r", "profiles": {"r": {"base_url": "https://api.example.com/v1", "model": "m"}}}
        with self.assertRaisesRegex(LLMError, "allow_remote"):
            llm.chat("x", [], cfg=cfg)

    def test_remote_allowed_sends_key_from_env_and_merges_settings(self):
        cfg = {"default_profile": "r", "tasks": {"t": "r"}, "profiles": {"r": {
            "base_url": "https://api.example.com/v1", "model": "big", "api_key_env": "PIPE_TEST_KEY", "allow_remote": True,
            "sampling": {"temperature": 0.3}, "extra_body": {"foo": 1}}}}
        seen = {}

        class R:
            def __enter__(s): return s
            def __exit__(s, *a): pass
            def read(s): return json.dumps({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {}}).encode()

        def urlopen(req, timeout):
            seen["auth"] = req.get_header("Authorization")
            seen["body"] = json.loads(req.data)
            seen["url"] = req.full_url
            return R()
        with mock.patch.dict("os.environ", {"PIPE_TEST_KEY": "sekret"}), mock.patch("urllib.request.urlopen", urlopen):
            r = llm.chat("t", [{"role": "user", "content": "hi"}], sampling={"max_tokens": 5}, cfg=cfg)
        self.assertEqual(r.text, "ok")
        self.assertEqual(seen["auth"], "Bearer sekret")
        self.assertEqual(seen["url"], "https://api.example.com/v1/chat/completions")
        self.assertEqual((seen["body"]["model"], seen["body"]["temperature"], seen["body"]["max_tokens"], seen["body"]["foo"]),
                         ("big", 0.3, 5, 1))

    def test_default_config_is_local_and_task_falls_back_to_default_profile(self):
        with mock.patch.dict("os.environ", {"PIPELINE_LLM_CONFIG": "/nonexistent/none.toml"}):
            with self.assertRaises(LLMError):
                llm.load_config()                       # an explicitly named but missing file is an error, not a silent default
        name, prof = llm.profile_for("anything", llm.DEFAULT)
        self.assertEqual(name, "local27b")
        self.assertTrue(llm.is_local(prof["base_url"]))

    def test_example_file_parses_and_defines_the_default_profile(self):
        import tomllib
        cfg = tomllib.loads((llm.CONFIG_DIR / "llm.example.toml").read_text(encoding="utf-8"))
        name, prof = llm.profile_for("structure_fallback", cfg)
        self.assertEqual(name, "local27b")
        self.assertFalse(prof["allow_remote"])


if __name__ == "__main__":
    unittest.main()
