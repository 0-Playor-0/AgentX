"""Minimal LLM client for the bench buyers (std-lib only): Gemini and Groq via their OpenAI-compatible
endpoints, with an on-disk cache, per-model token pacing (free-tier TPM), 429/5xx backoff and daily-quota fail-fast.

Keys: the cloud environment's network proxy injects saved keys, so a placeholder is sent when no variable is
set; otherwise GEMINI_API_KEY / GROQ_API_KEY from the environment or .env. Keys are never logged.
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
PROVIDERS = {
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "GEMINI_API_KEY", None),
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY", 7000),   # TPM budget (limit 8000)
}
STATS = {"calls": 0, "cached": 0, "retries": 0, "errors": 0, "tokens": 0}
_lock = threading.Lock()
_window = {}            # model -> [(time, tokens)]


def provider(model):
    return "gemini" if model.startswith(("gemini", "gemma")) else "groq"


def _key(var):
    k = os.environ.get(var)
    if not k and (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text().splitlines():
            if line.startswith(var + "="):
                k = line.split("=", 1)[1].strip()
    return k or "proxy-injected"


def _pace(model, tpm, need):
    """Block until `need` more tokens fit in this model's rolling one-minute budget."""
    if not tpm:
        return
    while True:
        with _lock:
            now = time.time()
            w = [(t, n) for t, n in _window.get(model, []) if now - t < 60]
            _window[model] = w
            if sum(n for _, n in w) + need <= tpm or not w:
                w.append((now, need))
                return
            wait = 60 - (now - w[0][0]) + 0.5
        time.sleep(max(0.5, wait))


def _settle(model, est, actual):
    with _lock:
        w = _window.get(model, [])
        for k in range(len(w) - 1, -1, -1):
            if w[k][1] == est:
                w[k] = (w[k][0], actual)
                break


def chat(messages, model="qwen/qwen3.8-27b", thinking=False, temperature=0.4, max_tokens=500, tag=""):
    """Returns the reply text. Cached by (request body, tag)."""
    prov = provider(model)
    url, var, tpm = PROVIDERS[prov]
    body = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens,
            "response_format": {"type": "json_object"}}
    if thinking:
        body["reasoning_effort"] = "low"
        body["max_tokens"] = max_tokens + 1500
    elif prov == "gemini" or model.startswith("qwen"):
        body["reasoning_effort"] = "none"
    else:
        body["reasoning_effort"] = "low"          # gpt-oss cannot turn thinking off; low is the minimum
    h = hashlib.sha256(json.dumps([body, tag], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]
    path = CACHE / f"{h}.json"
    if path.exists():
        STATS["cached"] += 1
        return json.loads(path.read_text())["text"]
    data = json.dumps(body).encode()
    est = len(data) // 3 + body["max_tokens"] // 2
    delay = 5.0
    for attempt in range(10):
        _pace(model, tpm, est)
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json",
                                                              "Authorization": "Bearer " + _key(var)})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                out = json.loads(resp.read())
            text = out["choices"][0]["message"].get("content") or ""
            used = (out.get("usage") or {}).get("total_tokens", est)
            _settle(model, est, used)
            STATS["calls"] += 1
            STATS["tokens"] += used
            CACHE.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"text": text, "model": model}, ensure_ascii=False))
            return text
        except urllib.error.HTTPError as e:
            msg = e.read()[:3000].decode("utf-8", "replace")
            low = msg.lower()
            if e.code == 429 and ("perday" in low or "per day" in low or "limit: 0" in low or "(rpd)" in low):
                STATS["errors"] += 1
                raise RuntimeError(f"daily quota exhausted for {model}") from None
            if e.code in (429, 500, 502, 503, 504):
                STATS["retries"] += 1
                ra = e.headers.get("retry-after") if e.headers else None
                try:
                    wait = float(ra) + 1 if ra else delay
                except ValueError:
                    wait = delay
                time.sleep(min(120.0, wait))
                delay = min(90.0, delay * 2)
                continue
            STATS["errors"] += 1
            raise RuntimeError(f"{prov} HTTP {e.code}: {msg[:300]}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            STATS["retries"] += 1
            time.sleep(delay)
            delay = min(90.0, delay * 2)
    STATS["errors"] += 1
    raise RuntimeError(f"{prov}: too many retries")
