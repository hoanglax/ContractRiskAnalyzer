"""One place that talks to a chat-completions API. Settings come from backend/llm.toml (see llm.example.toml),
PIPELINE_LLM_CONFIG, or the built-in default (the local 27B on :9876). Stdlib only.

    from application.adapters.llm import chat
    r = chat("structure_fallback", [{"role": "user", "content": "..."}])
    r.text, r.finish_reason, r.usage, r.profile, r.model

Contract text is private: a profile whose host is not this machine is refused unless it sets allow_remote = true."""
from __future__ import annotations

import json
import logging
import os
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parents[2]
DEFAULT = {
    "default_profile": "local27b",
    "tasks": {},
    "profiles": {"local27b": {
        "base_url": "http://127.0.0.1:9876/v1", "model": "local", "timeout_s": 600, "allow_remote": False,
        "sampling": {"temperature": 0, "max_tokens": 3000},
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}},
}
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


class LLMError(Exception):
    pass


@dataclass
class LLMResult:
    text: str
    finish_reason: str | None
    usage: dict
    profile: str
    model: str
    raw: dict = field(default_factory=dict, repr=False)


def config_path() -> Path | None:
    p = os.environ.get("PIPELINE_LLM_CONFIG")
    if p:
        return Path(p)
    p = CONFIG_DIR / "llm.toml"
    return p if p.exists() else None


def load_config() -> dict:
    p = config_path()
    if p is None:
        return DEFAULT
    try:
        cfg = tomllib.loads(p.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise LLMError(f"cannot read LLM config {p}: {e}") from e
    if not cfg.get("profiles"):
        raise LLMError(f"{p}: no [profiles.*] defined")
    return cfg


def profile_for(task: str, cfg: dict | None = None) -> tuple[str, dict]:
    cfg = cfg or load_config()
    name = cfg.get("tasks", {}).get(task) or cfg.get("default_profile")
    prof = cfg.get("profiles", {}).get(name)
    if prof is None:
        raise LLMError(f"task {task!r}: profile {name!r} is not defined")
    if "base_url" not in prof:
        raise LLMError(f"profile {name!r}: base_url missing")
    return name, prof


def is_local(base_url: str) -> bool:
    return (urllib.parse.urlparse(base_url).hostname or "") in _LOCAL_HOSTS


def chat(task: str, messages: list[dict], *, sampling: dict | None = None, cfg: dict | None = None) -> LLMResult:
    name, prof = profile_for(task, cfg)
    base = prof["base_url"].rstrip("/")
    if not is_local(base) and not prof.get("allow_remote", False):
        raise LLMError(f"profile {name!r} points at {base}, which is not this machine; "
                       "set allow_remote = true on that profile if contract text may be sent there")
    key = prof.get("api_key") or (os.environ.get(prof["api_key_env"], "") if prof.get("api_key_env") else "")
    body = {"model": prof.get("model", "local"), "messages": messages,
            **prof.get("sampling", {}), **prof.get("extra_body", {}), **(sampling or {})}
    headers = {"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})}
    req = urllib.request.Request(base + "/chat/completions", json.dumps(body).encode(), headers)
    t = time.monotonic()
    log.debug("%s -> %s %s: %d messages, %d chars", task, name, body["model"], len(messages),
              sum(len(m.get("content") or "") for m in messages))
    try:
        with urllib.request.urlopen(req, timeout=prof.get("timeout_s", 600)) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        err = LLMError(f"{name}: HTTP {e.code} {e.read()[:200]!r}")
        log.warning("%s -> %s %s: HTTP %s after %.1fs", task, name, body["model"], e.code, time.monotonic() - t)
        raise err from e
    except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError) as e:
        log.warning("%s -> %s %s: %s after %.1fs", task, name, body["model"], type(e).__name__, time.monotonic() - t)
        raise LLMError(f"{name}: {e}") from e
    try:
        ch = out["choices"][0]
        res = LLMResult(ch["message"]["content"] or "", ch.get("finish_reason"), out.get("usage", {}), name, body["model"], out)
    except (KeyError, IndexError, TypeError) as e:
        log.warning("%s -> %s %s: unexpected response shape", task, name, body["model"])
        raise LLMError(f"{name}: unexpected response shape") from e
    u = res.usage or {}
    log.info("%s -> %s %s: %.1fs, finish=%s, tokens in=%s out=%s%s", task, name, res.model, time.monotonic() - t,
             res.finish_reason, u.get("prompt_tokens", "?"), u.get("completion_tokens", "?"),
             f", cost ${u['cost']:.5f}" if isinstance(u.get("cost"), (int, float)) else "")
    return res
