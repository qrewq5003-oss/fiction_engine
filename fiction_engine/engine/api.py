"""
API клиенты: Anthropic, OpenAI, Gemini, DeepSeek (прямые) + nano-gpt.
"""

import os
from openai import OpenAI
import anthropic

# ─── Провайдеры ───────────────────────────────────────────────────────────────

PROVIDERS = {
    "anthropic_direct": {
        "label": "Anthropic",
        "placeholder": "sk-ant-api03-...",
        "hint": "console.anthropic.com → API Keys",
        "url": "https://console.anthropic.com",
    },
    "openai_direct": {
        "label": "OpenAI",
        "placeholder": "sk-proj-...",
        "hint": "platform.openai.com → API Keys",
        "url": "https://platform.openai.com",
    },
    "gemini_direct": {
        "label": "Google Gemini",
        "placeholder": "AIza...",
        "hint": "aistudio.google.com → Get API key",
        "url": "https://aistudio.google.com",
    },
    "deepseek_direct": {
        "label": "DeepSeek",
        "placeholder": "sk-...",
        "hint": "platform.deepseek.com → API Keys",
        "url": "https://platform.deepseek.com",
    },
    "nano_gpt": {
        "label": "nano-gpt.com",
        "placeholder": "nano-...",
        "hint": "nano-gpt.com → Account → API (300+ моделей)",
        "url": "https://nano-gpt.com",
    },
}

# ─── Модели ───────────────────────────────────────────────────────────────────

MODELS = {
    "anthropic_direct": {
        "label": "Anthropic (прямой)",
        "models": [
            {"id": "claude-opus-4-6",          "name": "Claude Opus 4.6 — лучший для текста"},
            {"id": "claude-sonnet-4-6",         "name": "Claude Sonnet 4.6 — баланс"},
            {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5 — быстрый/дешёвый"},
        ]
    },
    "openai_direct": {
        "label": "OpenAI (прямой)",
        "models": [
            {"id": "gpt-4o",       "name": "GPT-4o"},
            {"id": "gpt-4o-mini",  "name": "GPT-4o Mini — дешёвый"},
            {"id": "gpt-4-turbo",  "name": "GPT-4 Turbo"},
            {"id": "o3-mini",      "name": "o3-mini (reasoning)"},
            {"id": "o1",           "name": "o1 (reasoning)"},
        ]
    },
    "gemini_direct": {
        "label": "Google Gemini (прямой)",
        "models": [
            {"id": "gemini-2.0-flash",          "name": "Gemini 2.0 Flash — быстрый"},
            {"id": "gemini-2.0-flash-lite",     "name": "Gemini 2.0 Flash Lite — дешёвый"},
            {"id": "gemini-1.5-pro",            "name": "Gemini 1.5 Pro — большой контекст"},
            {"id": "gemini-1.5-flash",          "name": "Gemini 1.5 Flash"},
        ]
    },
    "deepseek_direct": {
        "label": "DeepSeek (прямой)",
        "models": [
            {"id": "deepseek-chat",     "name": "DeepSeek Chat (V3) — проза"},
            {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner (R1) — анализ"},
        ]
    },
    "nano_gpt": {
        "label": "nano-gpt.com",
        "groups": {
            "★ Лучшие для прозы": [
                {"id": "anthropic/claude-opus-4.6",     "name": "Claude Opus 4.6 ★"},
                {"id": "openai/gpt-5.2",                "name": "GPT-5.2 ★"},
                {"id": "gemini-2.5-pro",                "name": "Gemini 2.5 Pro ★"},
                {"id": "deepseek/deepseek-v3.2",        "name": "DeepSeek V3.2 ★"},
                {"id": "moonshotai/kimi-k2-instruct",   "name": "Kimi K2 ★"},
                {"id": "Sao10K/L3.3-70B-Euryale-v2.3", "name": "Euryale 70B ★ проза/RP"},
                {"id": "anthracite-org/magnum-v4-72b",   "name": "Magnum v4 72B ★ проза"},
                {"id": "zai-org/glm-5",                  "name": "GLM 5 ★"},
                {"id": "moonshotai/kimi-k2-thinking",    "name": "Kimi K2 Thinking ★"},
            ],
            "Claude": [
                {"id": "anthropic/claude-opus-4.6",     "name": "Claude Opus 4.6"},
                {"id": "anthropic/claude-sonnet-4.6",   "name": "Claude Sonnet 4.6"},
                {"id": "claude-opus-4-20250514",         "name": "Claude Opus 4"},
                {"id": "claude-sonnet-4-20250514",       "name": "Claude Sonnet 4"},
                {"id": "claude-3-7-sonnet-20250219",     "name": "Claude 3.7 Sonnet"},
                {"id": "claude-3-5-sonnet-20241022",     "name": "Claude 3.5 Sonnet"},
                {"id": "claude-3-7-sonnet-thinking",     "name": "Claude 3.7 Thinking"},
            ],
            "OpenAI GPT": [
                {"id": "openai/gpt-5.2",        "name": "GPT-5.2 — последний"},
                {"id": "openai/gpt-5.1",        "name": "GPT-5.1"},
                {"id": "openai/gpt-5",          "name": "GPT-5"},
                {"id": "openai/gpt-5-mini",     "name": "GPT-5 Mini"},
                {"id": "openai/gpt-4.1",        "name": "GPT-4.1"},
                {"id": "openai/gpt-4.1-mini",   "name": "GPT-4.1 Mini"},
                {"id": "openai/gpt-4o",         "name": "GPT-4o"},
                {"id": "openai/gpt-4o-mini",    "name": "GPT-4o Mini"},
                {"id": "openai/o3",             "name": "o3 (reasoning)"},
                {"id": "openai/o4-mini",        "name": "o4-mini (reasoning)"},
            ],
            "Google Gemini": [
                {"id": "gemini-2.5-pro",            "name": "Gemini 2.5 Pro — лучший"},
                {"id": "gemini-2.5-flash",          "name": "Gemini 2.5 Flash — быстрый"},
                {"id": "gemini-2.5-flash-lite",     "name": "Gemini 2.5 Flash Lite"},
                {"id": "gemini-3-pro-preview",      "name": "Gemini 3 Pro (preview)"},
                {"id": "gemini-2.0-flash-001",      "name": "Gemini 2.0 Flash"},
            ],
            "DeepSeek": [
                {"id": "deepseek/deepseek-v3.2",        "name": "DeepSeek V3.2 — лучший"},
                {"id": "deepseek-ai/DeepSeek-V3.1",     "name": "DeepSeek V3.1"},
                {"id": "deepseek-chat",                  "name": "DeepSeek Chat"},
                {"id": "deepseek-r1",                    "name": "DeepSeek R1 (reasoning)"},
                {"id": "deepseek-ai/DeepSeek-R1-0528",  "name": "DeepSeek R1-0528"},
                {"id": "deepseek-reasoner",              "name": "DeepSeek Reasoner"},
            ],
            "Mistral": [
                {"id": "mistralai/mistral-large",                     "name": "Mistral Large"},
                {"id": "mistralai/mistral-large-3-675b-instruct-2512","name": "Mistral Large 3 675B"},
                {"id": "mistralai/mistral-medium-3.1",                "name": "Mistral Medium 3.1"},
                {"id": "mistralai/mistral-small-creative",            "name": "Mistral Small Creative"},
                {"id": "Magistral-Small-2506",                        "name": "Magistral Small"},
            ],
            "Grok (xAI)": [
                {"id": "grok-3-beta",          "name": "Grok 3 Beta"},
                {"id": "grok-3-fast-beta",     "name": "Grok 3 Fast"},
                {"id": "x-ai/grok-4-fast",     "name": "Grok 4 Fast"},
            ],
            "Kimi (Moonshot)": [
                {"id": "moonshotai/kimi-k2-instruct",  "name": "Kimi K2 — нарратив"},
                {"id": "moonshotai/kimi-k2.5",         "name": "Kimi K2.5"},
                {"id": "moonshotai/kimi-k2-thinking",  "name": "Kimi K2 Thinking"},
            ],
            "GLM (Zhipu)": [
                {"id": "zai-org/glm-5",             "name": "GLM 5 — новейший"},
                {"id": "zai-org/glm-5:thinking",    "name": "GLM 5 Thinking"},
                {"id": "glm-4.7:cloud",             "name": "GLM 4.7"},
                {"id": "glm-4.7:thinking",          "name": "GLM 4.7 Thinking"},
                {"id": "glm-4.6:cloud",             "name": "GLM 4.6"},
                {"id": "glm-4.5:cloud",             "name": "GLM 4.5"},
                {"id": "glm-4.5:thinking",          "name": "GLM 4.5 Thinking"},
                {"id": "glm-4.5-air:cloud",         "name": "GLM 4.5 Air — быстрый"},
            ],
            "Qwen (Alibaba)": [
                {"id": "qwen/qwen3-235b-a22b",     "name": "Qwen3 235B"},
                {"id": "qwen/qwen3-32b",           "name": "Qwen3 32B"},
                {"id": "qwen/qwen3-30b-a3b",       "name": "Qwen3 30B MoE"},
                {"id": "qwen/qwen2.5-72b-instruct","name": "Qwen2.5 72B"},
                {"id": "qwen/qwq-32b",             "name": "QwQ 32B (reasoning)"},
                {"id": "qwen/qwen3.5-397b-a17b",   "name": "Qwen3.5 397B"},
            ],
            "Llama (Meta)": [
                {"id": "meta-llama/llama-4-maverick",       "name": "Llama 4 Maverick"},
                {"id": "meta-llama/llama-4-scout",          "name": "Llama 4 Scout"},
                {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Llama 3.3 70B"},
            ],
            "Специальные для прозы/RP": [
                {"id": "Sao10K/L3.3-70B-Euryale-v2.3",          "name": "Euryale 70B — проза/RP"},
                {"id": "TheDrummer/Cydonia-24B-v4.3",            "name": "Cydonia 24B"},
                {"id": "TheDrummer/Anubis-70B-v1.1",             "name": "Anubis 70B — нарратив"},
                {"id": "nousresearch/hermes-4-405b",             "name": "Hermes 4 405B"},
                {"id": "LatitudeGames/Wayfarer-Large-70B-Llama-3.3", "name": "Wayfarer 70B"},
                {"id": "anthracite-org/magnum-v4-72b",           "name": "Magnum v4 72B ★"},
                {"id": "anthracite-org/magnum-v2-72b",           "name": "Magnum v2 72B"},
                {"id": "MiniMaxAI/MiniMax-M2.5",                 "name": "MiniMax M2.5"},
                {"id": "nvidia/llama-3.3-nemotron-super-49b-v1", "name": "Nemotron Super 49B"},
                {"id": "nvidia/nemotron-ultra-253b-v1",          "name": "Nemotron Ultra 253B"},
                {"id": "deepseek-ai/DeepSeek-R1-Distill-Llama-70B", "name": "DeepSeek R1 Llama 70B"},
            ],
        }
    }
}


def get_all_models_flat():
    result = []
    for provider_key, provider in MODELS.items():
        if provider_key == "nano_gpt":
            for group, models in provider.get("groups", {}).items():
                for m in models:
                    result.append({
                        "value": f"nano_gpt::{m['id']}",
                        "label": f"[nano-gpt / {group}] {m['name']}",
                        "provider": "nano_gpt",
                        "model_id": m["id"],
                    })
        else:
            label = provider["label"]
            for m in provider["models"]:
                result.append({
                    "value": f"{provider_key}::{m['id']}",
                    "label": f"[{label}] {m['name']}",
                    "provider": provider_key,
                    "model_id": m["id"],
                })
    return result


def parse_model_value(model_value: str):
    parts = model_value.split("::", 1)
    if len(parts) != 2:
        raise ValueError(f"Неверный формат модели: {model_value}")
    return parts[0], parts[1]


# ─── Роутер ───────────────────────────────────────────────────────────────────

def call_model(model_value: str, system: str, user: str,
               anthropic_key: str = None, nano_key: str = None,
               openai_key: str = None, gemini_key: str = None,
               deepseek_key: str = None,
               max_tokens: int = 4096,
               prefill: str = "") -> str:
    """prefill — начало ответа модели (assistant prefill).
    Модель продолжает генерацию с этого текста, не может начать заново.
    Идеально для продолжения главы: передаём последние 200-300 слов."""
    provider, model_id = parse_model_value(model_value)

    if provider == "anthropic_direct":
        return _call_anthropic(model_id, system, user, anthropic_key, max_tokens, prefill)
    elif provider == "openai_direct":
        return _call_openai_direct(model_id, system, user, openai_key, max_tokens, prefill)
    elif provider == "gemini_direct":
        return _call_gemini_direct(model_id, system, user, gemini_key, max_tokens, prefill)
    elif provider == "deepseek_direct":
        return _call_deepseek_direct(model_id, system, user, deepseek_key, max_tokens, prefill)
    elif provider == "nano_gpt":
        return _call_nanogpt(model_id, system, user, nano_key, max_tokens, prefill)
    else:
        raise ValueError(f"Неизвестный провайдер: {provider}")


# ─── Клиенты ─────────────────────────────────────────────────────────────────

def _call_anthropic(model_id, system, user, api_key, max_tokens, prefill=""):
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError("Нет Anthropic API ключа")
    client = anthropic.Anthropic(api_key=key)
    messages = [{"role": "user", "content": user}]
    if prefill:
        messages.append({"role": "assistant", "content": prefill})
    msg = client.messages.create(
        model=model_id, max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    result = msg.content[0].text
    return (prefill + result) if prefill else result


def _call_openai_direct(model_id, system, user, api_key, max_tokens, prefill=""):
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("Нет OpenAI API ключа")
    client = OpenAI(api_key=key)
    resp = client.chat.completions.create(
        model=model_id, max_tokens=max_tokens,
        messages=(
            [{"role": "system", "content": system},
             {"role": "user",   "content": user},
             {"role": "assistant", "content": prefill}]
            if prefill else
            [{"role": "system", "content": system},
             {"role": "user",   "content": user}]
        ),
    )
    result = resp.choices[0].message.content
    return (prefill + result) if prefill else result


def _call_gemini_direct(model_id, system, user, api_key, max_tokens, prefill=""):
    # Gemini поддерживает OpenAI-совместимый endpoint
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise ValueError("Нет Google Gemini API ключа")
    client = OpenAI(
        api_key=key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    resp = client.chat.completions.create(
        model=model_id, max_tokens=max_tokens,
        messages=(
            [{"role": "system", "content": system},
             {"role": "user",   "content": user},
             {"role": "assistant", "content": prefill}]
            if prefill else
            [{"role": "system", "content": system},
             {"role": "user",   "content": user}]
        ),
    )
    result = resp.choices[0].message.content
    return (prefill + result) if prefill else result


def _call_deepseek_direct(model_id, system, user, api_key, max_tokens, prefill=""):
    # DeepSeek — OpenAI-совместимый API
    key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("Нет DeepSeek API ключа")
    client = OpenAI(
        api_key=key,
        base_url="https://api.deepseek.com/v1",
    )
    resp = client.chat.completions.create(
        model=model_id, max_tokens=max_tokens,
        messages=(
            [{"role": "system", "content": system},
             {"role": "user",   "content": user},
             {"role": "assistant", "content": prefill}]
            if prefill else
            [{"role": "system", "content": system},
             {"role": "user",   "content": user}]
        ),
    )
    result = resp.choices[0].message.content
    return (prefill + result) if prefill else result


def _call_nanogpt(model_id, system, user, api_key, max_tokens, prefill=""):
    key = api_key or os.environ.get("NANO_GPT_API_KEY")
    if not key:
        raise ValueError("Нет nano-gpt API ключа")
    client = OpenAI(
        api_key=key,
        base_url="https://nano-gpt.com/api/v1",
    )
    resp = client.chat.completions.create(
        model=model_id, max_tokens=max_tokens,
        messages=(
            [{"role": "system", "content": system},
             {"role": "user",   "content": user},
             {"role": "assistant", "content": prefill}]
            if prefill else
            [{"role": "system", "content": system},
             {"role": "user",   "content": user}]
        ),
    )
    result = resp.choices[0].message.content
    return (prefill + result) if prefill else result
