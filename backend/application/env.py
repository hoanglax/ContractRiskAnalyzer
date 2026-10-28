"""Read the project's .env (KEY=VALUE lines) into os.environ at startup, so API keys need no shell setup.

Variables already set in the environment win. Entry points (the API, CLIs) call load(); stdlib only.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT = REPO / ".env"


def load(path: Path = DEFAULT) -> list[str]:
    """Names of the variables it set (never their values)."""
    if not path.exists():
        return []
    set_ = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value
            set_.append(key)
    return set_
