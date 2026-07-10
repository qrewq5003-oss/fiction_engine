"""
engine/ai.py — AI-вызовы для планировщика.
Читает API ключи из БД Fiction Engine (~/.fiction_engine/projects.db или ~/fiction_engine/projects.db).
"""
import os
import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

FE_DB_PATH = Path.home() / "fiction_engine" / "projects.db"
DEFAULT_MAX_TOKENS = 800


def _get_fe_key(provider: str):
    if not FE_DB_PATH.exists():
        return None
    try:
        conn = sqlite3.connect(str(FE_DB_PATH))
        conn.row_factory = sqlite3.Row
        r = conn.execute("SELECT api_key FROM api_keys WHERE provider=?", (provider,)).fetchone()
        conn.close()
        return r["api_key"] if r else None
    except Exception as e:
        logger.error(f"Ошибка чтения ключа {provider}: {e}")
        return None


def _get_default_model():
    if not FE_DB_PATH.exists():
        return None
    try:
        conn = sqlite3.connect(str(FE_DB_PATH))
        conn.row_factory = sqlite3.Row
        r = conn.execute("SELECT value FROM settings WHERE key='model'").fetchone()
        conn.close()
        return r["value"] if r else None
    except Exception:
        return None


def get_available_models():
    provider_map = {
        "deepseek_direct": [
            {"value": "deepseek::deepseek-chat",     "label": "DeepSeek Chat"},
            {"value": "deepseek::deepseek-reasoner", "label": "DeepSeek Reasoner"},
        ],
        "anthropic_direct": [
            {"value": "anthropic::claude-sonnet-4-6",         "label": "Claude Sonnet 4.6"},
            {"value": "anthropic::claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5"},
        ],
        "openai_direct": [
            {"value": "openai::gpt-4o",      "label": "GPT-4o"},
            {"value": "openai::gpt-4o-mini", "label": "GPT-4o Mini"},
        ],
        "gemini_direct": [
            {"value": "gemini::gemini-2.0-flash", "label": "Gemini 2.0 Flash"},
        ],
        "nano_gpt": [
            {"value": "nano::deepseek/deepseek-chat-v3-0324:free", "label": "NanoGPT DeepSeek"},
        ],
    }
    return [m for p, models in provider_map.items() if _get_fe_key(p) for m in models]


def call(model_value: str, system: str, prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
    if not model_value:
        model_value = _get_default_model() or ""
    if not model_value:
        raise ValueError("Модель не указана")
    parts = model_value.split("::", 1)
    if len(parts) != 2:
        raise ValueError(f"Неверный формат модели: {model_value}")
    provider, model_name = parts[0].lower(), parts[1]
    if provider == "deepseek":
        return _call_deepseek(model_name, system, prompt, max_tokens)
    elif provider == "anthropic":
        return _call_anthropic(model_name, system, prompt, max_tokens)
    elif provider == "openai":
        return _call_openai(model_name, system, prompt, max_tokens)
    elif provider == "gemini":
        return _call_gemini(model_name, system, prompt, max_tokens)
    elif provider == "nano":
        return _call_nano(model_name, system, prompt, max_tokens)
    else:
        raise ValueError(f"Неизвестный провайдер: {provider}")


def _call_deepseek(model, system, prompt, max_tokens):
    key = _get_fe_key("deepseek_direct")
    if not key: raise ValueError("Нет API ключа DeepSeek в FE")
    import urllib.request, json
    body = json.dumps({"model": model, "messages": [{"role":"system","content":system},{"role":"user","content":prompt}], "max_tokens": max_tokens}).encode()
    req = urllib.request.Request("https://api.deepseek.com/v1/chat/completions", data=body,
          headers={"Content-Type":"application/json","Authorization":f"Bearer {key}"}, method="POST")
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def _call_anthropic(model, system, prompt, max_tokens):
    key = _get_fe_key("anthropic_direct")
    if not key: raise ValueError("Нет API ключа Anthropic в FE")
    import urllib.request, json
    body = json.dumps({"model": model, "max_tokens": max_tokens, "system": system,
                       "messages": [{"role":"user","content":prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
          headers={"Content-Type":"application/json","x-api-key":key,"anthropic-version":"2023-06-01"}, method="POST")
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())["content"][0]["text"]


def _call_openai(model, system, prompt, max_tokens):
    key = _get_fe_key("openai_direct")
    if not key: raise ValueError("Нет API ключа OpenAI в FE")
    import urllib.request, json
    body = json.dumps({"model": model, "messages": [{"role":"system","content":system},{"role":"user","content":prompt}], "max_tokens": max_tokens}).encode()
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=body,
          headers={"Content-Type":"application/json","Authorization":f"Bearer {key}"}, method="POST")
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def _call_gemini(model, system, prompt, max_tokens):
    key = _get_fe_key("gemini_direct")
    if not key: raise ValueError("Нет API ключа Gemini в FE")
    import urllib.request, json
    body = json.dumps({"contents":[{"parts":[{"text":f"{system}\n\n{prompt}"}]}],
                       "generationConfig":{"maxOutputTokens":max_tokens}}).encode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    req = urllib.request.Request(url, data=body, headers={"Content-Type":"application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())["candidates"][0]["content"]["parts"][0]["text"]


def _call_nano(model, system, prompt, max_tokens):
    key = _get_fe_key("nano_gpt")
    if not key: raise ValueError("Нет API ключа NanoGPT в FE")
    import urllib.request, json
    body = json.dumps({"model": model, "messages": [{"role":"system","content":system},{"role":"user","content":prompt}], "max_tokens": max_tokens}).encode()
    req = urllib.request.Request("https://nano-gpt.com/api/v1/chat/completions", data=body,
          headers={"Content-Type":"application/json","Authorization":f"Bearer {key}"}, method="POST")
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]
