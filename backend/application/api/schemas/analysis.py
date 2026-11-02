"""Pydantic schemas for the initial contract-upload API.

Draft v0.1. Keep upload response intentionally small: analysis_id + status.
The route/exception handler must enforce file-level validation separately.
"""
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AnalysisStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class UploadAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_id: UUID
    status: AnalysisStatus = AnalysisStatus.QUEUED


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="allow")

    field: str | None = None
    # Optional structured metadata, e.g. allowed_extensions or max_bytes.
    metadata: dict[str, Any] | None = None


class ApiError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, examples=["UNSUPPORTED_FILE_TYPE"])
    message: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class ApiErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ApiError
