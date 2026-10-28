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


PROSE = BODY.replace("Điều 1. ", "")
PAGE_TEXT = [
    "HỢP ĐỒNG THUÊ NHÀ\nTrang 1/3\nĐiều 1. Đối tượng\n" + PROSE + "Điều 2. Giá thuê\nBên B trả tiền thuê",
    "Trang 2/3\nhằng tháng vào ngày mùng năm.\n" + PROSE + "Điều 3. Thời hạn\n" + PROSE,
    "Trang 3/3\nĐiều 4. Chấm dứt\n" + PROSE,
]


class TestImageSet(unittest.TestCase):
    def run_set(self, transcribe, srcs=None, env=None):
        srcs = srcs or [PNG, PNG, PNG]
        with mock.patch.dict(ing.os.environ, env or {**ENV, "STRUCTURE_LLM": "off"}, clear=True), \
             mock.patch.object(vlm, "transcribe", side_effect=transcribe) as t:
            doc = ing.ingest_images(srcs, [f"img{i}.png" for i in range(1, len(srcs) + 1)])
        return doc, t

    @staticmethod
    def pages(texts):
        it = iter(texts)
        return lambda img, mime: (next(it), {"model": "vendor/vlm", "usage": {"n": 1}})

    def test_pages_joined_into_one_document(self):
        doc, t = self.run_set(self.pages(PAGE_TEXT))
        self.assertEqual(t.call_count, 3)
        self.assertEqual([p.n for p in doc.pages], [1, 2, 3])
        self.assertEqual({p.route for p in doc.pages}, {"vision"})
        self.assertEqual(doc.source["detected_type"], "images")
        self.assertEqual([f["filename"] for f in doc.source["files"]], ["img1.png", "img2.png", "img3.png"])
        self.assertEqual({b.page for b in doc.blocks}, {1, 2, 3})
        for b in doc.blocks:
            self.assertEqual(doc.text[b.char_start:b.char_end], b.text)
        self.assertNotIn("Trang 2/3", doc.text)                  # page numbers stripped as in PDFs
        self.assertEqual([c.label for c in doc.structure.clauses], ["Điều 1", "Điều 2", "Điều 3", "Điều 4"])
        self.assertFalse(any("no_marker_chain" in w or "not confident" in w for w in doc.warnings))

    def test_clause_runs_over_the_page_break(self):
        doc, _ = self.run_set(self.pages(PAGE_TEXT))
        d2 = doc.structure.clauses[1]
        self.assertIn("Bên B trả tiền thuê\nhằng tháng", doc.text[d2.char_start:d2.char_end])

    def test_one_failed_page_is_a_warning(self):
        texts = iter(PAGE_TEXT)

        def fake(img, mime):
            text = next(texts)
            if text.startswith("Trang 2/3"):
                raise vlm.VlmError("boom")
            return text, {"model": "vendor/vlm", "usage": None}

        doc, _ = self.run_set(fake)
        self.assertEqual(doc.pages[1].chars, 0)
        self.assertEqual(doc.raw["failed_pages"], [2])
        self.assertTrue(any(w.startswith("page 2 (img2.png): OCR failed") for w in doc.warnings))

    def test_every_page_failed_is_an_error(self):
        with self.assertRaises(IngestError) as cm:
            self.run_set(vlm.VlmError("boom"))
        self.assertEqual(cm.exception.reason, "conversion_failed")

    def test_non_image_rejected_before_any_model_call(self):
        with self.assertRaises(IngestError) as cm:
            self.run_set(self.pages(PAGE_TEXT), srcs=[PNG, b"%PDF-1.7 fake", PNG])
        self.assertEqual(cm.exception.reason, "unsupported_type")
        self.assertIn("page 2 (img2.png)", cm.exception.message)

    def test_without_engine_is_not_implemented(self):
        with self.assertRaises(IngestError) as cm:
            self.run_set(self.pages(PAGE_TEXT), env={"OCR_ENGINE": "off"})
        self.assertEqual(cm.exception.reason, "not_implemented")

    def test_identity_depends_on_page_order(self):
        jpeg = b"\xff\xd8\xff" + b"1" * 64
        a, _ = self.run_set(self.pages(PAGE_TEXT), srcs=[PNG, jpeg, PNG])
        b, _ = self.run_set(self.pages(PAGE_TEXT), srcs=[jpeg, PNG, PNG])
        self.assertNotEqual(a.source["sha256"], b.source["sha256"])


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
