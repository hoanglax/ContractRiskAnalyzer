import asyncio
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastapi import BackgroundTasks, HTTPException

from application.adapters import llm
from application.api import analyses
from application.config import Settings, settings
from application.modules.ingestion import ingest
from application.modules.ingestion import vlm
from application.modules.ingestion.ingest import IngestError


class TestSettings(unittest.TestCase):
    def test_defaults(self):
        configured = Settings.from_env({})
        self.assertEqual(configured.MAX_FILE_SIZE_MB, 50)
        self.assertEqual(configured.MAX_FILE_SIZE_BYTES, 50 * 1024 * 1024)
        self.assertEqual(configured.MAX_PDF_PAGES, 200)
        self.assertEqual(configured.MAX_IMAGE_PAGES, 40)
        self.assertEqual(configured.UPLOAD_TIMEOUT_SECONDS, 30)
        self.assertEqual(configured.PARSER_TIMEOUT_SECONDS, 120)
        self.assertEqual(configured.PDF_INFO_TIMEOUT_SECONDS, 60)
        self.assertEqual(configured.OCR_TIMEOUT_SECONDS, 180)
        self.assertEqual(configured.LLM_TIMEOUT_SECONDS, 600)
        self.assertEqual(configured.RERANK_TIMEOUT_SECONDS, 300)
        self.assertEqual(configured.DETECTION_RETRIES, 2)
        self.assertEqual(configured.OCR_ENGINE, "auto")

    def test_environment_values_and_paths(self):
        configured = Settings.from_env({
            "MAX_FILE_SIZE_MB": "3",
            "MAX_PDF_PAGES": "12",
            "UPLOAD_TIMEOUT_SECONDS": "9",
            "OCR_TIMEOUT_SECONDS": "45",
            "OCR_ENGINE": "off",
            "DATA_DIR": "fixtures",
            "LEGAL_CORPUS_DIR": "fixtures/corpus",
        })
        self.assertEqual(configured.MAX_FILE_SIZE_BYTES, 3 * 1024 * 1024)
        self.assertEqual(configured.MAX_PDF_PAGES, 12)
        self.assertEqual(configured.UPLOAD_TIMEOUT_SECONDS, 9)
        self.assertEqual(configured.OCR_TIMEOUT_SECONDS, 45)
        self.assertEqual(configured.OCR_ENGINE, "off")
        self.assertIsInstance(configured.PROJECT_ROOT, Path)
        self.assertEqual(configured.DATA_DIR, configured.PROJECT_ROOT / "fixtures")
        self.assertEqual(configured.LEGAL_CORPUS_DIR, configured.PROJECT_ROOT / "fixtures" / "corpus")
        self.assertEqual(configured.LEGAL_VECTORS_DIR, configured.DATA_DIR / "legal_vectors")

    def test_zero_retries_are_allowed(self):
        configured = Settings.from_env({"OCR_RETRIES": "0", "LLM_RETRIES": "0"})
        self.assertEqual(configured.OCR_RETRIES, 0)
        self.assertEqual(configured.LLM_RETRIES, 0)

    def test_invalid_integer_values_are_rejected(self):
        for key in ("MAX_FILE_SIZE_MB", "MAX_PDF_PAGES", "MAX_IMAGE_PAGES",
                    "UPLOAD_TIMEOUT_SECONDS", "PARSER_TIMEOUT_SECONDS", "PDF_INFO_TIMEOUT_SECONDS",
                    "OCR_TIMEOUT_SECONDS", "LLM_TIMEOUT_SECONDS", "RERANK_TIMEOUT_SECONDS"):
            for value in ("0", "-1", "invalid"):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    Settings.from_env({key: value})
        for key in ("OCR_RETRIES", "LLM_RETRIES", "DETECTION_RETRIES"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                Settings.from_env({key: "-1"})

    def test_invalid_ocr_engine_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "OCR_ENGINE"):
            Settings.from_env({"OCR_ENGINE": "enabled"})

    def test_ingestion_uses_configured_file_size(self):
        configured = Settings.from_env({"MAX_FILE_SIZE_MB": "1"})
        with mock.patch.object(ingest, "MAX_BYTES", configured.MAX_FILE_SIZE_BYTES):
            with self.assertRaises(IngestError) as error:
                ingest._load(b"x" * (1024 * 1024 + 1), "large.txt")
        self.assertEqual(error.exception.reason, "too_large")

    def test_pdf_page_limit_is_checked_before_parsing(self):
        configured = Settings.from_env({"MAX_PDF_PAGES": "1"})
        with mock.patch.object(ingest, "settings", configured), \
             mock.patch.object(ingest, "_pdf_page_count", return_value=2), \
             mock.patch.object(ingest, "_pdftotext") as parse:
            with self.assertRaises(IngestError) as error:
                ingest.route_pdf(b"%PDF", ingest.Document(text="", source={}))
        self.assertEqual(error.exception.reason, "too_large")
        parse.assert_not_called()

    def test_parser_timeout_comes_from_settings(self):
        configured = Settings.from_env({"PARSER_TIMEOUT_SECONDS": "7"})
        result = SimpleNamespace(stdout=b"page\f", stderr=b"", returncode=0)
        with mock.patch.object(ingest, "settings", configured), \
             mock.patch.object(ingest.shutil, "which", return_value="pdftotext"), \
             mock.patch.object(ingest.subprocess, "run", return_value=result) as run:
            ingest._pdftotext(b"%PDF", layout=False)
        self.assertEqual(run.call_args.kwargs["timeout"], 7)

    def test_ocr_timeout_comes_from_settings(self):
        configured = Settings.from_env({"OCR_TIMEOUT_SECONDS": "9", "OCR_RETRIES": "0"})
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "choices": [{"message": {"content": "text"}}],
        }).encode()
        with mock.patch.object(vlm, "settings", configured), \
             mock.patch.dict(vlm.os.environ, {"OCR_API_KEY": "test", "OCR_MODEL": "test-model"}), \
             mock.patch.object(vlm.urllib.request, "urlopen", return_value=response) as urlopen:
            vlm.transcribe(b"image", "image/png")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 9)

    def test_llm_timeout_comes_from_settings(self):
        configured = Settings.from_env({"LLM_TIMEOUT_SECONDS": "11"})
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = (
            b'{"choices":[{"message":{"content":"text"}}]}')
        profile = {"default_profile": "local", "profiles": {
            "local": {"base_url": "http://127.0.0.1:1234/v1"},
        }}
        with mock.patch.object(llm, "settings", configured), \
             mock.patch.object(llm.urllib.request, "urlopen", return_value=response) as urlopen:
            llm.chat("test", [{"role": "user", "content": "hello"}], cfg=profile)
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 11)

    def test_upload_timeout_returns_request_timeout(self):
        class SlowUpload:
            async def read(self, _size):
                await asyncio.sleep(2)
                return b"data"

        configured = Settings.from_env({"UPLOAD_TIMEOUT_SECONDS": "1"})
        with mock.patch.object(analyses, "settings", configured):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(analyses.create_analysis(SlowUpload(), BackgroundTasks()))
        self.assertEqual(error.exception.status_code, 408)

    def test_module_settings_match_shared_settings(self):
        self.assertIsInstance(settings.PROJECT_ROOT, Path)
        self.assertIsInstance(settings.LEGAL_CORPUS_DIR, Path)
        self.assertIsInstance(settings.LEGAL_VECTORS_DIR, Path)
        self.assertIsInstance(settings.TAXONOMY_DIR, Path)
