"""M3 entry point: the one function the pipeline calls.

    from application.modules.detection.pipeline import run
    out = run(doc)    # -> {"mode", "findings": [Finding], "warnings", "error", "attempts"}

The risks looked for are the whole taxonomy (the closed set). How the calls are split is the mode: "group" (one
call per taxonomy group, the default) or "all" (every code in one call); DETECTION_MODE overrides the default.
Which model answers is the LLM config's "detect" task (llm.example.toml), not a setting here.
"""
from __future__ import annotations

import os

from application.modules.detection import whole_doc
from application.modules.detection.lens import from_taxonomy
from application.modules.ingestion.ingest import Document
from application.modules.taxonomy import taxonomy

MODES = {"group": whole_doc.detect_by_group, "all": whole_doc.detect}
DEFAULT_MODE = "group"


def run(doc: Document, *, mode: str | None = None, tax: taxonomy.Taxonomy | None = None) -> dict:
    """Findings that passed the gate, contract order first (missing ones last), plus the detector's warnings,
    error (None, or why nothing could be read) and every model call for the run record."""
    mode = mode or os.environ.get("DETECTION_MODE") or DEFAULT_MODE
    if mode not in MODES:
        raise ValueError(f"unknown detection mode {mode!r}; one of {sorted(MODES)}")
    res = MODES[mode](doc, from_taxonomy(tax or taxonomy.load()))
    findings = sorted(res["kept"], key=lambda f: (f.kind != "present", f.char_start or 0, f.code))
    return {"mode": mode, "findings": findings, "warnings": res["warnings"], "error": res["error"],
            "attempts": res["attempts"]}
