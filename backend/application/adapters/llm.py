"""One place that talks to a chat-completions API. Settings come from backend/llm.toml (see llm.example.toml),
PIPELINE_LLM_CONFIG, or the built-in default (the local 27B on :9876). Stdlib only.

    from application.adapters.llm import chat
    r = chat("structure_fallback", [{"role": "user", "content": "..."}])
    r.text, r.finish_reason, r.usage, r.profile, r.model

Contract text is private: a profile whose host is not this machine is refused unless it sets allow_remote = true.
Transient failures (429, 5xx, timeouts) are retried with backoff (`retries` per profile). `max_concurrency` per
profile says how many calls the pipeline may have in flight at once (1 for a one-slot local server)."""
from __future__ import annotations

import json
import logging
import os
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
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


RETRIES = 3                                  # per call, for the transient failures below; a profile can set "retries"
RETRY_STATUS = {429, 500, 502, 503, 504}     # rate limit, overload, gateway: worth waiting for; other 4xx are not
BACKOFF = (2, 6, 15)                         # seconds before retry 1, 2, 3 (then the last value)


def _backoff(attempt: int, retry_after: str | None) -> float:
    """The server's Retry-After (seconds, capped at 60) when it gives one, else the fixed schedule."""
    try:
        if retry_after is not None:
            return min(60.0, max(0.0, float(retry_after)))
    except ValueError:
        pass
    return float(BACKOFF[min(attempt, len(BACKOFF) - 1)])


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


def concurrency(task: str) -> int:
    """How many calls for `task` may run at once: the profile's max_concurrency, default 1."""
    try:
        return max(1, int(profile_for(task)[1].get("max_concurrency", 1)))
    except (LLMError, ValueError):
        return 1


def map_calls(task: str, fn, items: list) -> list:
    """fn over items, up to concurrency(task) at a time, results in input order. fn does the model call(s)."""
    n = concurrency(task)
    if n == 1 or len(items) < 2:
        return [fn(x) for x in items]
    with ThreadPoolExecutor(max_workers=min(n, len(items)), thread_name_prefix=task) as pool:
        return list(pool.map(fn, items))


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
    retries = int(prof.get("retries", RETRIES))
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=prof.get("timeout_s", 600)) as r:
                out = json.load(r)
            break
        except urllib.error.HTTPError as e:
            err, transient = LLMError(f"{name}: HTTP {e.code} {e.read()[:200]!r}"), e.code in RETRY_STATUS
            wait_hint = e.headers.get("Retry-After") if e.headers else None
            what = f"HTTP {e.code}"
        except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError) as e:
            err, transient, wait_hint, what = LLMError(f"{name}: {e}"), True, None, type(e).__name__
        if not transient or attempt == retries:
            log.warning("%s -> %s %s: %s after %.1fs%s", task, name, body["model"], what, time.monotonic() - t,
                        f", gave up after {attempt + 1} tries" if transient else "")
            raise err
        wait = _backoff(attempt, wait_hint)
        log.warning("%s -> %s %s: %s, retry %d/%d in %.0fs", task, name, body["model"], what, attempt + 1, retries, wait)
        time.sleep(wait)
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
