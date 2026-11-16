"""Central application settings, read from environment variables at startup."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _positive_int(name: str, value: str | None, default: int) -> int:
    try:
        parsed = default if value is None else int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return parsed


def _nonnegative_int(name: str, value: str | None, default: int) -> int:
    try:
        parsed = default if value is None else int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a non-negative integer") from exc
    if parsed < 0:
        raise ValueError(f"{name} must be zero or greater")
    return parsed


def _validate_ocr_engine(value: str) -> str:
    engine = value.lower()
    if engine not in {"auto", "vlm", "off"}:
        raise ValueError("OCR_ENGINE must be one of: auto, vlm, off")
    return engine


def _path(value: str | None, default: Path, root: Path) -> Path:
    path = Path(value) if value else default
    if not path.is_absolute():
        path = root / path
    return path.resolve()


@dataclass(frozen=True)
class Settings:
    MAX_FILE_SIZE_MB: int
    MAX_PDF_PAGES: int
    MAX_IMAGE_PAGES: int
    UPLOAD_TIMEOUT_SECONDS: int
    PARSER_TIMEOUT_SECONDS: int
    PDF_INFO_TIMEOUT_SECONDS: int
    OCR_TIMEOUT_SECONDS: int
    LLM_TIMEOUT_SECONDS: int
    RERANK_TIMEOUT_SECONDS: int
    OCR_RETRIES: int
    LLM_RETRIES: int
    DETECTION_RETRIES: int
    OCR_ENGINE: str
    PROJECT_ROOT: Path
    BACKEND_DIR: Path
    DATA_DIR: Path
    LEGAL_CORPUS_DIR: Path
    LEGAL_VECTORS_DIR: Path
    TAXONOMY_DIR: Path
    RUNS_DIR: Path

    @property
    def MAX_FILE_SIZE_BYTES(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    def current_ocr_engine(self) -> str:
        return _validate_ocr_engine(os.environ.get("OCR_ENGINE", self.OCR_ENGINE))

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ
        root = _path(env.get("PROJECT_ROOT"), _PROJECT_ROOT, _PROJECT_ROOT)
        backend = _path(env.get("BACKEND_DIR"), root / "backend", root)
        data = _path(env.get("DATA_DIR"), root / "data", root)
        ocr_engine = _validate_ocr_engine(env.get("OCR_ENGINE", "auto"))

        return cls(
            MAX_FILE_SIZE_MB=_positive_int("MAX_FILE_SIZE_MB", env.get("MAX_FILE_SIZE_MB"), 50),
            MAX_PDF_PAGES=_positive_int("MAX_PDF_PAGES", env.get("MAX_PDF_PAGES"), 200),
            MAX_IMAGE_PAGES=_positive_int("MAX_IMAGE_PAGES", env.get("MAX_IMAGE_PAGES"), 40),
            UPLOAD_TIMEOUT_SECONDS=_positive_int(
                "UPLOAD_TIMEOUT_SECONDS", env.get("UPLOAD_TIMEOUT_SECONDS"), 30),
            PARSER_TIMEOUT_SECONDS=_positive_int(
                "PARSER_TIMEOUT_SECONDS", env.get("PARSER_TIMEOUT_SECONDS"), 120),
            PDF_INFO_TIMEOUT_SECONDS=_positive_int(
                "PDF_INFO_TIMEOUT_SECONDS", env.get("PDF_INFO_TIMEOUT_SECONDS"), 60),
            OCR_TIMEOUT_SECONDS=_positive_int("OCR_TIMEOUT_SECONDS", env.get("OCR_TIMEOUT_SECONDS"), 180),
            LLM_TIMEOUT_SECONDS=_positive_int("LLM_TIMEOUT_SECONDS", env.get("LLM_TIMEOUT_SECONDS"), 600),
            RERANK_TIMEOUT_SECONDS=_positive_int(
                "RERANK_TIMEOUT_SECONDS", env.get("RERANK_TIMEOUT_SECONDS"), 300),
            OCR_RETRIES=_nonnegative_int("OCR_RETRIES", env.get("OCR_RETRIES"), 2),
            LLM_RETRIES=_nonnegative_int("LLM_RETRIES", env.get("LLM_RETRIES"), 3),
            DETECTION_RETRIES=_nonnegative_int(
                "DETECTION_RETRIES", env.get("DETECTION_RETRIES"), 2),
            OCR_ENGINE=ocr_engine,
            PROJECT_ROOT=root,
            BACKEND_DIR=backend,
            DATA_DIR=data,
            LEGAL_CORPUS_DIR=_path(env.get("LEGAL_CORPUS_DIR"), data / "legal_corpus", root),
            LEGAL_VECTORS_DIR=_path(env.get("LEGAL_VECTORS_DIR"), data / "legal_vectors", root),
            TAXONOMY_DIR=_path(env.get("TAXONOMY_DIR"), data / "taxonomy", root),
            RUNS_DIR=_path(env.get("RUNS_DIR"), backend / "runs", root),
        )


settings = Settings.from_env()