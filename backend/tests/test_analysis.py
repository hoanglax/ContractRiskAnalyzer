import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from application.adapters.llm import LLMError, LLMResult
from application.analysis import run
from application.main import app

CONTRACT = ("HỢP ĐỒNG THUÊ PHÒNG\nĐiều 1. Tiền cọc\nBên B đặt cọc 2 tháng tiền thuê. Bên A không hoàn trả tiền cọc "
            "trong mọi trường hợp.\nĐiều 2. Lãi chậm trả\nBên B chậm trả thì chịu lãi 2% mỗi ngày trên số tiền chậm trả.\n"
            "Điều 3. Điều khoản chung\nHai bên cam kết thực hiện đúng các điều khoản trên; hợp đồng lập thành 02 bản "
            "có giá trị như nhau, mỗi bên giữ 01 bản.\n").encode()


def reply(obj):
    return LLMResult(json.dumps(obj, ensure_ascii=False), "stop", {}, "p", "m")


def fake_chat(task, messages, **kw):
    """detect answers for the DEP group only; legal_pick picks C1; explain writes a valid explanation."""
    prompt = messages[0]["content"]
    if task == "detect":
        if "[B-DEP-04]" in prompt:
            return reply({"findings": [{"code": "B-DEP-04", "kind": "present", "issue": "mất cọc",
                                        "quote": "Bên A không hoàn trả tiền cọc trong mọi trường hợp."}]})
        return reply({"findings": []})
    if task == "legal_pick":
        return reply({"basis": [{"id": "C1", "why": "đặt cọc"}]})
    return reply({"summary": "Bạn có thể mất cọc [L1].", "recommendation": "Đề nghị ghi rõ thời hạn hoàn cọc."})


class FakeRetriever:
    def search(self, query, k=5, law=None):
        return []


class Analysis(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        for target, value in [(run, Path(d.name)), ]:
            p = mock.patch.object(target, "RUNS_DIR", value)
            p.start()
            self.addCleanup(p.stop)
        for p in (mock.patch.dict(os.environ, {"STRUCTURE_LLM": "off"}),
                  mock.patch("application.modules.legal_basis.basis.default_retriever",
                             return_value=(FakeRetriever(), [])),
                  mock.patch("application.adapters.llm.chat", side_effect=fake_chat)):
            p.start()
            self.addCleanup(p.stop)
        self.client = TestClient(app)

    def test_post_then_poll_gives_the_whole_result(self):
        r = self.client.post("/analyses", files={"file": ("hd.txt", CONTRACT, "text/plain")})
        self.assertEqual(r.status_code, 201)
        rid = r.json()["id"]
        rec = self.client.get(f"/analyses/{rid}").json()      # TestClient runs the background task before returning
        self.assertEqual((rec["status"], rec["error"]), ("done", None), rec.get("error"))
        self.assertEqual([f["code"] for f in rec["findings"]], ["B-DEP-04"])
        item = rec["items"][0]
        self.assertEqual((item["codes"], item["clause"]), (["B-DEP-04"], "Điều 1"))
        self.assertIn("Bạn có thể mất cọc", item["explanation"]["summary"])
        self.assertEqual(item["risks"][0]["severity"], "HIGH")       # the row, for the UI
        self.assertEqual(len(rec["calls"]["detect"]), 7)       # one per taxonomy group
        self.assertIn("detect", rec["versions"]["models"])
        self.assertIn("text", rec["document"])

    def test_unreadable_file_fails_with_the_ingest_code(self):
        rid = self.client.post("/analyses", files={"file": ("x.txt", b"ngan qua", "text/plain")}).json()["id"]
        rec = self.client.get(f"/analyses/{rid}").json()
        self.assertEqual((rec["status"], rec["stage"], rec["error"]["code"]), ("failed", "ingest", "no_text"))

    def test_model_down_fails_detection_but_a_later_stage_only_warns(self):
        with mock.patch("application.adapters.llm.chat", side_effect=LLMError("p: HTTP 503")):
            rid = self.client.post("/analyses", files={"file": ("hd.txt", CONTRACT, "text/plain")}).json()["id"]
        rec = self.client.get(f"/analyses/{rid}").json()
        self.assertEqual((rec["status"], rec["error"]["code"]), ("failed", "llm_error"))

        def explain_down(task, messages, **kw):
            if task == "explain":
                raise LLMError("p: HTTP 503")
            return fake_chat(task, messages, **kw)
        with mock.patch("application.adapters.llm.chat", side_effect=explain_down):
            rid = self.client.post("/analyses", files={"file": ("hd.txt", CONTRACT, "text/plain")}).json()["id"]
        rec = self.client.get(f"/analyses/{rid}").json()
        self.assertEqual(rec["status"], "done")
        self.assertIsNone(rec["items"][0]["explanation"])
        self.assertTrue(any("HTTP 503" in w["message"] for w in rec["warnings"] if w["stage"] == "explain"))

    def test_unknown_or_malicious_ids_are_404(self):
        for rid in ("0123456789ab", "..%2F..%2Fllm", "x" * 12):
            self.assertEqual(self.client.get(f"/analyses/{rid}").status_code, 404, rid)
        self.assertEqual(self.client.post("/analyses", files={"file": ("e.txt", b"", "text/plain")}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
