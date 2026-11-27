"""Nối model — chỗ DUY NHẤT trong bản chạy thử gọi model AI.

Hợp đồng (giữ nguyên để khung đo được token):
    call_model(system: str, user: str) -> dict với 4 khoá:
        "text": str
        "model": str
        "tokens_in": int
        "tokens_out": int

Chỉ dùng thư viện chuẩn của Python 3.10+.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from tracing import model_call

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOW_RAW = False


def load_env(path: str = os.path.join(ROOT, ".env")) -> None:
    """Đọc file .env (KEY=VALUE mỗi dòng) vào biến môi trường, không ghi đè biến đã có."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()
API_KEY = (
    os.environ.get("API_KEY")
    or os.environ.get("GEMINI_API_KEY")
    or os.environ.get("OPENAI_API_KEY")
    or os.environ.get("ANTHROPIC_API_KEY")
    or ""
).strip()

_raw_provider = (os.environ.get("MODEL_PROVIDER") or "").strip().lower()
if not _raw_provider:
    if os.environ.get("GEMINI_API_KEY"):
        MODEL_PROVIDER = "gemini"
    elif os.environ.get("OPENAI_API_KEY"):
        MODEL_PROVIDER = "openai"
    elif os.environ.get("ANTHROPIC_API_KEY"):
        MODEL_PROVIDER = "anthropic"
    else:
        MODEL_PROVIDER = "fake"
else:
    MODEL_PROVIDER = _raw_provider

MODEL_NAME = (os.environ.get("MODEL_NAME") or "").strip()
if not MODEL_NAME:
    if MODEL_PROVIDER == "gemini":
        MODEL_NAME = "gemini-2.5-flash-lite"
    elif MODEL_PROVIDER == "openai":
        MODEL_NAME = "gpt-4o-mini"
    elif MODEL_PROVIDER == "anthropic":
        MODEL_NAME = "claude-3-5-haiku-latest"

API_BASE_URL = (os.environ.get("API_BASE_URL") or "").strip()


def post_json(url: str, headers: dict[str, str], body: dict, timeout: int = 60) -> dict:
    """Gửi POST JSON, tự thử lại khi gặp HTTP 429/503 tạm thời."""
    payload = json.dumps(body).encode("utf-8")
    merged_headers = {"Content-Type": "application/json", **headers}
    last_err: Exception | None = None
    for attempt in range(2):
        req = urllib.request.Request(url, data=payload, method="POST", headers=merged_headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if SHOW_RAW:
                print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])
            return data
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", "replace")[:350]
            last_err = RuntimeError(f"HTTP {e.code}: {err_body}")
            if e.code in (429, 503) and attempt == 0:
                time.sleep(3.0)
                continue
            raise last_err from e
        except urllib.error.URLError as e:
            last_err = RuntimeError(f"URLError: {e.reason}")
            if attempt == 0:
                time.sleep(1.5)
                continue
            raise last_err from e
    assert last_err is not None
    raise last_err


def call_gemini(system: str, user: str, model_name: str) -> dict:
    """Gọi Gemini REST API (generateContent), lấy token thật từ usageMetadata."""
    if not API_KEY:
        raise RuntimeError("Thiếu API_KEY / GEMINI_API_KEY trong file .env")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    body: dict = {
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
            "maxOutputTokens": 2048,
        },
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    data = post_json(url, {"x-goog-api-key": API_KEY}, body)

    candidates = data.get("candidates") or []
    text = ""
    if candidates:
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(
            p.get("text", "")
            for p in parts
            if isinstance(p, dict) and not p.get("thought")
        )
    usage = data.get("usageMetadata") or {}
    tokens_in = int(usage.get("promptTokenCount") or 0)
    tokens_out = int(usage.get("candidatesTokenCount") or 0) + int(
        usage.get("thoughtsTokenCount") or 0
    )
    return {"text": text, "tokens_in": tokens_in, "tokens_out": tokens_out}


def call_openai(system: str, user: str, model_name: str) -> dict:
    """Gọi OpenAI hoặc API tương thích chuẩn OpenAI."""
    if not API_KEY:
        raise RuntimeError("Thiếu API_KEY / OPENAI_API_KEY trong file .env")
    url = API_BASE_URL or "https://api.openai.com/v1/chat/completions"
    messages = (
        [{"role": "system", "content": system}] if system else []
    ) + [{"role": "user", "content": user}]
    body = {
        "model": model_name,
        "messages": messages,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    data = post_json(url, {"Authorization": "Bearer " + API_KEY}, body)
    usage = data.get("usage") or {}
    text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    return {
        "text": text,
        "tokens_in": int(usage.get("prompt_tokens") or 0),
        "tokens_out": int(usage.get("completion_tokens") or 0),
    }


def call_claude(system: str, user: str, model_name: str) -> dict:
    """Gọi Anthropic Claude Messages API."""
    if not API_KEY:
        raise RuntimeError("Thiếu API_KEY / ANTHROPIC_API_KEY trong file .env")
    url = "https://api.anthropic.com/v1/messages"
    body = {
        "model": model_name,
        "max_tokens": 2048,
        "temperature": 0.1,
        "system": system or "",
        "messages": [{"role": "user", "content": user}],
    }
    data = post_json(
        url,
        {"x-api-key": API_KEY, "anthropic-version": "2023-06-01"},
        body,
    )
    text = "".join(
        b.get("text", "")
        for b in data.get("content", [])
        if isinstance(b, dict) and b.get("type") == "text"
    )
    usage = data.get("usage") or {}
    return {
        "text": text,
        "tokens_in": int(usage.get("input_tokens") or 0),
        "tokens_out": int(usage.get("output_tokens") or 0),
    }


def call_ollama(system: str, user: str, model_name: str) -> dict:
    """Gọi Ollama cục bộ."""
    url = API_BASE_URL or "http://localhost:11434/api/chat"
    messages = (
        [{"role": "system", "content": system}] if system else []
    ) + [{"role": "user", "content": user}]
    data = post_json(
        url,
        {},
        {"model": model_name, "messages": messages, "stream": False, "format": "json"},
        timeout=300,
    )
    return {
        "text": (data.get("message") or {}).get("content") or "",
        "tokens_in": int(data.get("prompt_eval_count") or 0),
        "tokens_out": int(data.get("eval_count") or 0),
    }


@model_call
def call_model(system: str, user: str, model_override: str | None = None) -> dict:
    """Điểm gọi model duy nhất cho agent. Trả dict có text, model, tokens_in, tokens_out."""
    if MODEL_PROVIDER == "fake":
        last = (user.strip().splitlines() or [""])[-1]
        return {
            "text": "[câu trả lời giả — chưa nối model] " + last[:60],
            "model": "fake",
            "tokens_in": 0,
            "tokens_out": 0,
        }

    chosen_model = (model_override or MODEL_NAME).strip()
    if MODEL_PROVIDER in ("gemini", "google"):
        res = call_gemini(system, user, chosen_model)
    elif MODEL_PROVIDER in ("openai", "deepseek", "openrouter"):
        res = call_openai(system, user, chosen_model)
    elif MODEL_PROVIDER in ("anthropic", "claude"):
        res = call_claude(system, user, chosen_model)
    elif MODEL_PROVIDER == "ollama":
        res = call_ollama(system, user, chosen_model)
    else:
        raise NotImplementedError(
            f"MODEL_PROVIDER={MODEL_PROVIDER} chưa được hỗ trợ trong codebase/ai.py"
        )

    return {
        "text": res["text"],
        "model": chosen_model,
        "tokens_in": int(res["tokens_in"]),
        "tokens_out": int(res["tokens_out"]),
    }
