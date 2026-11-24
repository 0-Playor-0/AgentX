"""Minimal Gemini client (OpenAI-compatible endpoint, std-lib only) with an on-disk cache and 429 backoff.

The key is read from GEMINI_API_KEY (environment, then .env). In the cloud environment the network proxy
injects the saved key, so a placeholder is used when no variable is set. The key is never logged.
"""
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "bench" / "cache"
URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
STATS = {"calls": 0, "cached": 0, "retries": 0, "errors": 0}
_lock = threading.Lock()
_last = [0.0]


def _key():
    k = os.environ.get("GEMINI_API_KEY")
    if not k and (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text().splitlines():
            if line.startswith("GEMINI_API_KEY="):
                k = line.split("=", 1)[1].strip()
    return k or "proxy-injected"


def chat(messages, model="gemini-2.5-flash", thinking=False, temperature=0.4, max_tokens=600, min_gap=0.0,
         tag=""):
    """Returns the reply text. Cached by (model, thinking, temperature, messages, tag)."""
    body = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens,
            "response_format": {"type": "json_object"}}
    if not thinking:
        body["reasoning_effort"] = "none"
    else:
        body["reasoning_effort"] = "low"
        body["max_tokens"] = max_tokens + 2048
    h = hashlib.sha256(json.dumps([body, tag], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]
    path = CACHE / f"{h}.json"
    if path.exists():
        STATS["cached"] += 1
        return json.loads(path.read_text())["text"]
    data = json.dumps(body).encode()
    delay = 5.0
    for attempt in range(8):
        with _lock:                                    # global pacing for free-tier RPM limits
            wait = _last[0] + min_gap - time.time()
            if wait > 0:
                time.sleep(wait)
            _last[0] = time.time()
        req = urllib.request.Request(URL, data=data, headers={"Content-Type": "application/json",
                                                              "Authorization": "Bearer " + _key()})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                out = json.loads(resp.read())
            text = out["choices"][0]["message"].get("content") or ""
            STATS["calls"] += 1
            CACHE.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"text": text, "model": model}, ensure_ascii=False))
            return text
        except urllib.error.HTTPError as e:
            msg = e.read()[:3000].decode("utf-8", "replace")
            if e.code == 429 and ("PerDay" in msg or "per day" in msg.lower() or "limit: 0" in msg):
                STATS["errors"] += 1
                raise RuntimeError(f"Gemini daily quota exhausted for {model}") from None
            if e.code in (429, 500, 502, 503, 504):
                STATS["retries"] += 1
                time.sleep(delay)
                delay = min(90.0, delay * 2)
                continue
            STATS["errors"] += 1
            raise RuntimeError(f"Gemini HTTP {e.code}: {msg}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            STATS["retries"] += 1
            time.sleep(delay)
            delay = min(90.0, delay * 2)
    STATS["errors"] += 1
    raise RuntimeError("Gemini: too many retries")
