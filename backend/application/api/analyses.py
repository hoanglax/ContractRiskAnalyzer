"""POST /analyses (a contract file) -> 201 {"id", "status"}; GET /analyses/{id} -> the run record (poll it).

The analysis runs in the background in this process (application.analysis.run); see orch_api.mmd.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile
from fastapi.responses import FileResponse

from application.analysis import run

router = APIRouter(prefix="/analyses", tags=["analyses"])
demo = APIRouter()
DEMO_PAGE = Path(__file__).with_name("demo.html")


@demo.get("/demo", include_in_schema=False)
def demo_page() -> FileResponse:
    """A one-file demo UI (upload, progress, result) until the real frontend exists; /demo?id=<run> reopens a run."""
    return FileResponse(DEMO_PAGE)


@router.post("", status_code=201)
async def create_analysis(file: UploadFile, background: BackgroundTasks) -> dict:
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty file")
    rid = run.create(data, file.filename or "upload")
    background.add_task(run.analyze, rid)
    return {"id": rid, "status": "queued"}


@router.get("/{rid}")
def get_analysis(rid: str) -> dict:
    try:
        return run.load(rid)
    except run.UnknownRun:
        raise HTTPException(404, "no such analysis") from None
