"""Logging setup for the backend. Modules only do `log = logging.getLogger(__name__)`; entry points (the API, CLIs)
call setup() once.

    LOG_LEVEL   DEBUG | INFO (default) | WARNING ...
    LOG_FILE    also append to this file

Contract text is private, so log lines carry codes, counts, timings and reasons, never contract or statute text,
quotes or model replies (those live in the run record).
"""
from __future__ import annotations

import logging
import os

FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup(level: str | None = None, file: str | None = None) -> None:
    """Idempotent: a second call only changes the level."""
    root = logging.getLogger("application")
    root.setLevel((level or os.environ.get("LOG_LEVEL") or "INFO").upper())
    if getattr(root, "_configured", False):
        return
    fmt = logging.Formatter(FORMAT, "%H:%M:%S")
    handlers = [logging.StreamHandler()]
    if file or os.environ.get("LOG_FILE"):
        handlers.append(logging.FileHandler(file or os.environ["LOG_FILE"], encoding="utf-8"))
    for h in handlers:
        h.setFormatter(fmt)
        root.addHandler(h)
    root.propagate = False
    root._configured = True
