"""One analysis of one contract: M1 ingest -> M3 detect -> M4 legal basis -> M6 explain, recorded in runs/<id>.json.

    rid = create(data, filename)    # saves the upload, status "queued"
    analyze(rid)                    # runs every stage (the API does this in the background)
    load(rid)                       # the record

The record is rewritten after every stage, so a poller sees progress and a failed run keeps what it had:
  {"id", "created", "status": queued | running | done | failed, "stage", "error": {code, message} | null,
   "warnings": [{stage, message}], "document", "findings", "bases", "items", "calls": {stage: [...]}, "versions"}
A run fails when the file cannot be read (IngestError, with its code) or detection gets nothing readable from the
model; a failed legal-basis or explanation call is a warning on that item. Runs go one at a time: the local model
serves one request at a time and embedded Qdrant allows one user per process, so later ones wait as "queued".

RUNS_DIR (env) moves the records; default backend/runs (git-ignored).
"""
from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import logging
import os
import re
import subprocess
import threading
import time
import traceback
import uuid
from pathlib import Path

from application.adapters import llm
from application.modules.detection import pipeline as detection, whole_doc
from application.modules.explain import explain as m6
from application.modules.ingestion.ingest import IngestError, ingest
from application.modules.legal_basis import basis as m4
from application.modules.taxonomy import taxonomy

log = logging.getLogger(__name__)
BACKEND = Path(__file__).resolve().parents[2]
RUNS_DIR = Path(os.environ.get("RUNS_DIR") or BACKEND / "runs")
TASKS = ("structure_fallback", "detect", "legal_pick", "explain")
PROMPTS = {"detect": whole_doc.PROMPT, "detect_fix": whole_doc.FIX, "legal_pick": m4.PROMPT, "explain": m6.PROMPT}
_ID = re.compile(r"[0-9a-f]{12}")
_one_at_a_time = threading.Lock()


class UnknownRun(KeyError):
    pass


def _path(rid: str) -> Path:
    if not _ID.fullmatch(rid or ""):          # ids come from URLs: never let one name another file
        raise UnknownRun(rid)
    return RUNS_DIR / f"{rid}.json"


def _save(rec: dict) -> None:
    p = _path(rec["id"])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    tmp.replace(p)                            # a poller never reads a half-written file


def load(rid: str) -> dict:
    p = _path(rid)
    if not p.exists():
        raise UnknownRun(rid)
    return json.loads(p.read_text(encoding="utf-8"))


def create(data: bytes, filename: str) -> str:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    rid = uuid.uuid4().hex[:12]
    (RUNS_DIR / f"{rid}.upload").write_bytes(data)
    _save({"id": rid, "created": datetime.datetime.now().isoformat(timespec="seconds"), "filename": filename,
           "status": "queued", "stage": None, "error": None, "warnings": [], "document": None, "findings": [],
           "bases": [], "items": [], "calls": {}, "versions": versions()})
    log.info("run %s: queued %s (%d bytes)", rid, filename, len(data))
    return rid


def versions() -> dict:
    """What produced a result, to compare runs later: code, prompts, taxonomy, and the model behind each task."""
    def git(*args):
        try:
            r = subprocess.run(["git", *args], cwd=BACKEND, capture_output=True, text=True, timeout=5)
            return r.stdout.strip() if r.returncode == 0 else None
        except OSError:
            return None
    models = {}
    for t in TASKS:
        try:
            name, prof = llm.profile_for(t)
            models[t] = {"profile": name, "model": prof.get("model"), "base_url": prof.get("base_url")}
        except llm.LLMError as e:
            models[t] = {"error": str(e)}
    tax = taxonomy.DEFAULT_JSON
    return {"commit": git("rev-parse", "--short", "HEAD"), "dirty": bool(git("status", "--porcelain", "--", ".")),
            "prompts": {k: hashlib.sha256(v.encode()).hexdigest()[:12] for k, v in PROMPTS.items()},
            "taxonomy": hashlib.sha256(tax.read_bytes()).hexdigest()[:12] if tax.exists() else None,
            "models": models}


def _document(doc) -> dict:
    d = dataclasses.asdict(doc)
    d.pop("raw", None)                        # per-page OCR provenance: large, and only for debugging ingest
    d.pop("blocks", None)
    return d


def analyze(rid: str) -> dict:
    """Run every stage of a queued run; never raises (a failure is recorded in the run)."""
    rec = load(rid)
    with _one_at_a_time:
        t0 = time.monotonic()
        rec["status"] = "running"

        def stage(name):
            rec["stage"] = name
            _save(rec)
            log.info("run %s: %s", rid, name)

        def warn(stage_name, messages):
            rec["warnings"] += [{"stage": stage_name, "message": m} for m in messages]

        def fail(code, message):
            rec.update(status="failed", error={"code": code, "message": message})
            _save(rec)
            log.warning("run %s failed at %s: %s %s", rid, rec["stage"], code, message)
            return rec

        try:
            stage("ingest")
            upload = RUNS_DIR / f"{rid}.upload"
            try:
                doc = ingest(upload.read_bytes(), rec["filename"])
            except IngestError as e:
                return fail(e.reason, e.message)
            rec["document"] = _document(doc)
            warn("ingest", doc.warnings)

            stage("detect")
            try:
                det = detection.run(doc)
            except llm.LLMError as e:
                return fail("llm_error", str(e))
            rec["calls"]["detect"] = det["attempts"]
            warn("detect", det["warnings"])
            if det["error"]:
                return fail("detection_failed", det["error"])
            rec["findings"] = [dataclasses.asdict(f) for f in det["findings"]]

            stage("legal_basis")
            bases = m4.attach(det["findings"])
            rec["bases"] = [{**{k: v for k, v in b.items() if k != "attempt"},
                             "basis": [dataclasses.asdict(x) for x in b["basis"]]} for b in bases["items"]]
            rec["calls"]["legal_pick"] = [b["attempt"] for b in bases["items"] if b["attempt"]]
            warn("legal_basis", bases["warnings"] + [w for b in bases["items"] for w in b["warnings"]])

            stage("explain")
            ex = m6.explain(doc, det["findings"], bases["items"])
            rec["items"] = [{**dataclasses.asdict(it), "basis": [{**dataclasses.asdict(b), "label": b.label}
                                                                 for b in it.basis]} for it in ex["items"]]
            rec["calls"]["explain"] = ex["attempts"]
            warn("explain", ex["warnings"] + [w for it in ex["items"] for w in it.warnings])

            rec.update(status="done", stage=None, seconds=round(time.monotonic() - t0))
            _save(rec)
            log.info("run %s: done, %d items, %d warnings, %ds", rid, len(rec["items"]), len(rec["warnings"]),
                     rec["seconds"])
            return rec
        except Exception as e:              # a bug must still end the run, or the poller waits forever
            log.error("run %s: unexpected error\n%s", rid, traceback.format_exc())
            return fail("internal", f"{type(e).__name__}: {e}")
