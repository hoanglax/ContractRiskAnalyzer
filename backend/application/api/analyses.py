"""POST /analyses (a contract file) -> 201 {"id", "status"}; GET /analyses/{id} -> the run record (poll it).

The analysis runs in the background in this process (application.analysis.run); see orch_api.mmd.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile

from application.analysis import run

router = APIRouter(prefix="/analyses", tags=["analyses"])


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
