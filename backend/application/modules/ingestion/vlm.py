"""OCR through a vision-language model (any OpenAI-compatible chat endpoint,
e.g. OpenRouter). Which model is a deployment choice, not a code one.

Env:
  OCR_ENGINE    auto (default) | vlm | off.  auto = vlm when key and model are set.
  OCR_API_KEY   bearer token
  OCR_MODEL     model id, e.g. "provider/model-name"
  OCR_BASE_URL  default https://openrouter.ai/api/v1
  OCR_EXTRA_BODY  JSON merged into the request, for model-specific switches, e.g.
                  {"chat_template_kwargs": {"enable_thinking": false}} for a local Qwen3.5
"""
import base64
import json
import os
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
TIMEOUT = 180
RETRIES = 2

PROMPT = (
    "Transcribe this page of a Vietnamese contract exactly as written. "
    "Output plain text only: no commentary, no markdown, no bold markers. "
    "Transcribe every line from the first to the last; never skip, merge or summarise lines. "
    "Keep the original line breaks and numbering (Điều, khoản, a), b), 1.). "
    "Keep capital letters exactly as printed (a heading in capitals stays in capitals). "
    "Write each table row on one line with cells separated by ' | '. "
    "Keep every diacritic. Do not correct, translate, summarise or add anything. "
    "Write [?] for any character, word or field you cannot read, and also for any "
    "blacked-out, blurred or redacted field; never write the word 'redacted'. "
    "Write [QR: ?] only where a QR code is printed. "
    "Include handwritten signatures or names as written, or [?] if unreadable. "
    "Skip stamps and watermarks that are not text of the contract."
)


def strip_markdown(text: str) -> str:
    """Models sometimes bold words despite the prompt; the page text has no markup."""
    return text.replace("**", "")


class VlmError(Exception):
    """The model call failed; the message is safe to show as a warning."""


def engine() -> str:
    """'vlm' or 'off' after resolving OCR_ENGINE."""
    choice = os.environ.get("OCR_ENGINE", "auto").lower()
    if choice == "off":
        return "off"
    if choice == "vlm" or (os.environ.get("OCR_API_KEY") and os.environ.get("OCR_MODEL")):
        return "vlm"
    return "off"


def model_name() -> str:
    return os.environ.get("OCR_MODEL", "")


def transcribe(image: bytes, mime: str) -> tuple[str, dict]:
    """One page image -> (text, usage info). Raises VlmError."""
    key, model = os.environ.get("OCR_API_KEY"), os.environ.get("OCR_MODEL")
    if not key or not model:
        raise VlmError("OCR_API_KEY and OCR_MODEL must be set for vision OCR")
    url = os.environ.get("OCR_BASE_URL", DEFAULT_BASE_URL).rstrip("/") + "/chat/completions"
    try:
        extra = json.loads(os.environ.get("OCR_EXTRA_BODY") or "{}")
    except json.JSONDecodeError:
        raise VlmError("OCR_EXTRA_BODY is not valid JSON") from None
    body = json.dumps({
        "model": model,
        "temperature": 0,
        **extra,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url",
             "image_url": {"url": f"data:{mime};base64,{base64.b64encode(image).decode()}"}},
        ]}],
    }).encode()
    req = urllib.request.Request(url, body, {"Authorization": f"Bearer {key}",
                                             "Content-Type": "application/json"})
    last = ""
    for attempt in range(RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                payload = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code not in (429, 500, 502, 503, 504):
                raise VlmError(f"vision OCR request failed ({last})") from None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last = type(e).__name__
        if attempt < RETRIES:
            time.sleep(2 ** attempt)
    else:
        raise VlmError(f"vision OCR request failed after {RETRIES + 1} tries ({last})")
    try:
        choice = payload["choices"][0]
        text = choice["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise VlmError("vision OCR returned an unexpected response") from None
    if choice.get("finish_reason") == "length":
        raise VlmError("vision OCR output was cut off (page too long for the model)")
    return strip_markdown(text).strip(), {"model": payload.get("model", model), "usage": payload.get("usage")}
