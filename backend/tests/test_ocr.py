import json
import unittest
import urllib.error
from unittest import mock

from application.modules.ingestion import ingest as ing
from application.modules.ingestion import vlm
from application.modules.ingestion.ingest import IngestError, ingest

BODY = ("Điều 1. Bên A cho Bên B thuê căn hộ theo các điều khoản dưới đây. "
        "Bên B có trách nhiệm thanh toán tiền thuê đúng hạn vào ngày mùng năm hằng tháng.\n") * 4
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
ENV = {"OCR_ENGINE": "auto", "OCR_API_KEY": "k", "OCR_MODEL": "vendor/vlm"}


class TestEngine(unittest.TestCase):
    def test_auto_needs_key_and_model(self):
        with mock.patch.dict(vlm.os.environ, {"OCR_ENGINE": "auto"}, clear=True):
            self.assertEqual(vlm.engine(), "off")
        with mock.patch.dict(vlm.os.environ, ENV, clear=True):
            self.assertEqual(vlm.engine(), "vlm")

    def test_off_wins(self):
        with mock.patch.dict(vlm.os.environ, {**ENV, "OCR_ENGINE": "off"}, clear=True):
            self.assertEqual(vlm.engine(), "off")


class _Resp:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def read(self):
        return json.dumps(self.payload).encode()


def _ok(text, finish="stop"):
    return _Resp({"model": "vendor/vlm", "usage": {"total_tokens": 5},
                  "choices": [{"finish_reason": finish, "message": {"content": text}}]})


class TestTranscribe(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict(vlm.os.environ, ENV, clear=True)
        p.start()
        self.addCleanup(p.stop)
        s = mock.patch.object(vlm.time, "sleep")
        s.start()
        self.addCleanup(s.stop)

    def test_request_shape_and_result(self):
        with mock.patch.object(vlm.urllib.request, "urlopen", return_value=_ok(" Hợp đồng \n")) as u:
            text, info = vlm.transcribe(PNG, "image/png")
        self.assertEqual(text, "Hợp đồng")
        req = u.call_args[0][0]
        body = json.loads(req.data)
        self.assertEqual(body["model"], "vendor/vlm")
        self.assertTrue(body["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(req.get_header("Authorization"), "Bearer k")
        self.assertEqual(info["model"], "vendor/vlm")

    def test_bold_markers_stripped(self):
        with mock.patch.object(vlm.urllib.request, "urlopen", return_value=_ok("Bên **A** chịu")):
            self.assertEqual(vlm.transcribe(PNG, "image/png")[0], "Bên A chịu")

    def test_retries_transient_errors(self):
        err = urllib.error.HTTPError("u", 429, "rate", {}, None)
        with mock.patch.object(vlm.urllib.request, "urlopen", side_effect=[err, _ok("ok")]):
            self.assertEqual(vlm.transcribe(PNG, "image/png")[0], "ok")

    def test_gives_up_after_retries(self):
        err = urllib.error.HTTPError("u", 503, "down", {}, None)
        with mock.patch.object(vlm.urllib.request, "urlopen", side_effect=err) as u:
            with self.assertRaises(vlm.VlmError):
                vlm.transcribe(PNG, "image/png")
        self.assertEqual(u.call_count, vlm.RETRIES + 1)

    def test_client_error_not_retried(self):
        err = urllib.error.HTTPError("u", 401, "no", {}, None)
        with mock.patch.object(vlm.urllib.request, "urlopen", side_effect=err) as u:
            with self.assertRaises(vlm.VlmError):
                vlm.transcribe(PNG, "image/png")
        self.assertEqual(u.call_count, 1)

    def test_truncated_output_rejected(self):
        with mock.patch.object(vlm.urllib.request, "urlopen", return_value=_ok("x", "length")):
            with self.assertRaises(vlm.VlmError):
                vlm.transcribe(PNG, "image/png")

    def test_bad_response_shape(self):
        with mock.patch.object(vlm.urllib.request, "urlopen", return_value=_Resp({"oops": 1})):
            with self.assertRaises(vlm.VlmError):
                vlm.transcribe(PNG, "image/png")

    def test_missing_config(self):
        with mock.patch.dict(vlm.os.environ, {}, clear=True):
            with self.assertRaises(vlm.VlmError):
                vlm.transcribe(PNG, "image/png")


class TestImageRoute(unittest.TestCase):
    def test_without_engine_is_not_implemented(self):
        with mock.patch.dict(ing.os.environ, {"OCR_ENGINE": "off"}, clear=True):
            with self.assertRaises(IngestError) as cm:
                ingest(PNG, filename="a.png")
        self.assertEqual(cm.exception.reason, "not_implemented")

    def test_image_to_document(self):
        with mock.patch.dict(ing.os.environ, ENV, clear=True), \
             mock.patch.object(vlm, "transcribe", return_value=(BODY, {"model": "vendor/vlm", "usage": None})):
            doc = ingest(PNG, filename="a.png")
        self.assertEqual(doc.pages[0].route, "vision")
        self.assertTrue(any("vision model" in w for w in doc.warnings))
        for b in doc.blocks:
            self.assertEqual(doc.text[b.char_start:b.char_end], b.text)

    def test_vlm_failure_is_conversion_failed(self):
        with mock.patch.dict(ing.os.environ, ENV, clear=True), \
             mock.patch.object(vlm, "transcribe", side_effect=vlm.VlmError("boom")):
            with self.assertRaises(IngestError) as cm:
                ingest(PNG, filename="a.png")
        self.assertEqual(cm.exception.reason, "conversion_failed")


class TestScannedPdf(unittest.TestCase):
    def run_pages(self, pages, transcribe):
        with mock.patch.dict(ing.os.environ, ENV, clear=True), \
             mock.patch.object(ing, "_pdftotext", return_value=pages), \
             mock.patch.object(ing, "_pdf_page_count", return_value=len(pages)), \
             mock.patch.object(ing, "_render_page", return_value=PNG), \
             mock.patch.object(vlm, "transcribe", side_effect=transcribe):
            return ingest(b"%PDF-1.7 fake", filename="x.pdf")

    def test_scanned_page_is_ocrd_in_place(self):
        calls = []

        def fake(img, mime):
            calls.append(mime)
            return "Trang quét: " + BODY, {"model": "vendor/vlm", "usage": None}

        doc = self.run_pages([BODY * 3, "", BODY * 3], fake)
        self.assertEqual(len(calls), 1)
        self.assertEqual([p.route for p in doc.pages], ["native", "vision", "native"])
        self.assertIn("Trang quét", doc.text)
        self.assertTrue(any("pages 2 were read by a vision model" in w for w in doc.warnings))
        for b in doc.blocks:
            self.assertEqual(doc.text[b.char_start:b.char_end], b.text)

    def test_ocr_failure_keeps_going_with_warning(self):
        def fake(img, mime):
            raise vlm.VlmError("boom")

        doc = self.run_pages([BODY * 3, "", BODY * 3], fake)
        self.assertEqual([p.route for p in doc.pages], ["native"] * 3)
        self.assertTrue(any("page 2" in w and "OCR failed" in w for w in doc.warnings))

    def test_good_pdf_never_calls_the_model(self):
        def fake(img, mime):
            raise AssertionError("should not be called")

        doc = self.run_pages([BODY * 3, BODY * 3], fake)
        self.assertEqual([p.route for p in doc.pages], ["native"] * 2)


if __name__ == "__main__":
    unittest.main()
