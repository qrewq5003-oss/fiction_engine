"""
API клиенты: Anthropic, OpenAI, Gemini, DeepSeek (прямые) + nano-gpt.
"""

import os
from contextvars import ContextVar
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
            "★ Проверенные — отвечают и пишут главу": [
                # Замер 2026-09-13. ВАЖНАЯ ПОПРАВКА к первой редакции этого
                # списка: пять прогонов одной модели на одном промпте с одним
                # судьёй дали 37 · 30 · 29 · 26 (и один отказ). Вместе с
                # прежними замерами: 26 · 26 · 29 · 30 · 32 · 33 · 37.
                # Стандартное отклонение 4.0 балла, размах 11 на шкале 50.
                #
                # Значит по ОДНОМУ прогону различим только сдвиг от ~8 баллов.
                # Первая редакция ранжировала эту группу по одному прогону
                # (33 против 32 против 29) — такой разницы измерение не
                # различает, и порядок был выдуман. Оценок в подписях больше
                # нет: между этими пятью выбор по баллам не обоснован.
                #
                # Что замер ВЫДЕРЖАЛ и почему они здесь: все пятеро отвечают
                # по ключу и пишут главу целиком. Модели, писавшие по 370-440
                # слов вместо 2500-3000, отстают на 15-22 балла — это вдвое
                # больше разброса, и такой разрыв измерению доступен.
                {"id": "z-ai/glm-5.3",                   "name": "GLM 5.3 ★"},
                {"id": "moonshotai/kimi-k2.5",           "name": "Kimi K2.5 ★ самая многословная из проверенных"},
                {"id": "deepseek/deepseek-v4-pro-0813",  "name": "DeepSeek V4 Pro ★ самая быстрая из проверенных"},
                {"id": "moonshotai/kimi-k2-thinking",    "name": "Kimi K2 Thinking ★"},
                {"id": "deepseek-ai/DeepSeek-V3.1",      "name": "DeepSeek V3.1 ★"},
            ],
            "Claude": [
                {"id": "anthropic/claude-opus-4.6",     "name": "Claude Opus 4.6"},
                {"id": "anthropic/claude-sonnet-4.6",   "name": "Claude Sonnet 4.6"},
                {"id": "claude-opus-4-20250514",         "name": "Claude Opus 4"},
                {"id": "claude-sonnet-4-20250514",       "name": "Claude Sonnet 4"},
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
            ],
            "DeepSeek": [
                {"id": "deepseek/deepseek-v4-pro-0813", "name": "DeepSeek V4 Pro 0813 — ровный объём, сильный диалог"},
                {"id": "deepseek/deepseek-v4-pro",      "name": "DeepSeek V4 Pro"},
                {"id": "deepseek/deepseek-v4-flash",    "name": "DeepSeek V4 Flash — быстрый"},
                {"id": "deepseek/deepseek-v3.2",        "name": "DeepSeek V3.2 — много текста, диалог 3/10"},
                {"id": "deepseek-ai/DeepSeek-V3.1",     "name": "DeepSeek V3.1"},
                {"id": "deepseek-chat",                  "name": "DeepSeek Chat"},
                {"id": "deepseek-r1",                    "name": "DeepSeek R1 (reasoning)"},
                {"id": "deepseek-ai/DeepSeek-R1-0528",  "name": "DeepSeek R1-0528"},
                {"id": "deepseek-reasoner",              "name": "DeepSeek Reasoner"},
            ],
            "Mistral": [
                {"id": "mistralai/mistral-large",                     "name": "Mistral Large"},
                {"id": "mistralai/mistral-large-3-675b-instruct-2512","name": "Mistral Large 3 675B — 760 слов в замере"},
                {"id": "mistralai/mistral-medium-3.1",                "name": "Mistral Medium 3.1"},
                {"id": "Magistral-Small-2506",                        "name": "Magistral Small"},
            ],
            "Kimi (Moonshot)": [
                {"id": "moonshotai/kimi-k2-instruct",  "name": "Kimi K2 — нарратив"},
                {"id": "moonshotai/kimi-k2.5",         "name": "Kimi K2.5"},
                {"id": "moonshotai/kimi-k2-thinking",  "name": "Kimi K2 Thinking"},
            ],
            "GLM (Zhipu)": [
                {"id": "z-ai/glm-5.3",              "name": "GLM 5.3 — новейший"},
                {"id": "z-ai/glm-5.3:thinking",     "name": "GLM 5.3 Thinking"},
                {"id": "z-ai/glm-5.2",              "name": "GLM 5.2"},
                {"id": "z-ai/glm-5.1",              "name": "GLM 5.1"},
                {"id": "zai-org/glm-5",             "name": "GLM 5"},
                {"id": "zai-org/glm-5:thinking",    "name": "GLM 5 Thinking"},
                {"id": "glm-4.7:cloud",             "name": "GLM 4.7 — много текста, слабый голос"},
                {"id": "glm-4.7:thinking",          "name": "GLM 4.7 Thinking — 11 минут на главу"},
                {"id": "glm-4.6:cloud",             "name": "GLM 4.6"},
                {"id": "glm-4.5:thinking",          "name": "GLM 4.5 Thinking"},
            ],
            "Qwen (Alibaba)": [
                {"id": "qwen/qwen3-235b-a22b",     "name": "Qwen3 235B"},
                {"id": "qwen/qwen3-32b",           "name": "Qwen3 32B"},
                {"id": "qwen/qwen3-30b-a3b",       "name": "Qwen3 30B MoE"},
                {"id": "qwen/qwen2.5-72b-instruct","name": "Qwen2.5 72B"},
                {"id": "qwen/qwen3.5-397b-a17b",   "name": "Qwen3.5 397B — 16 минут на главу"},
            ],
            "Llama (Meta)": [
                {"id": "meta-llama/llama-4-maverick",       "name": "Llama 4 Maverick — заметно слабее проверенных"},
                {"id": "meta-llama/llama-4-scout",          "name": "Llama 4 Scout"},
                {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Llama 3.3 70B"},
            ],
            "Специальные для прозы/RP": [
                {"id": "Sao10K/L3.3-70B-Euryale-v2.3",          "name": "Euryale 70B — 11/50 в замере, 440 слов"},
                {"id": "TheDrummer/Cydonia-24B-v4.3",            "name": "Cydonia 24B"},
                {"id": "TheDrummer/Anubis-70B-v1.1",             "name": "Anubis 70B — 21/50 в замере, 370 слов"},
                {"id": "nousresearch/hermes-4-405b",             "name": "Hermes 4 405B — без прямой речи в замере"},
                {"id": "LatitudeGames/Wayfarer-Large-70B-Llama-3.3", "name": "Wayfarer 70B — не принимает промпт master"},
                {"id": "anthracite-org/magnum-v4-72b",           "name": "Magnum v4 72B — в тарифе нет; v2 дала 15/50"},
                {"id": "anthracite-org/magnum-v2-72b",           "name": "Magnum v2 72B — 15/50 в замере, 390 слов"},
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

# ─── Причина остановки последнего вызова ──────────────────────────────────────
#
# SDK возвращают stop_reason (Anthropic) / finish_reason (OpenAI-совместимые),
# но call_model по контракту отдаёт строку — менять сигнатуру значит трогать
# весь pipeline и contracts.LLMCaller. Поэтому причина кладётся в ContextVar:
# он изолирован по потокам, а генерация как раз идёт в фоновых потоках.
# Читать сразу после вызова — через get_last_stop_reason().

_last_stop_reason: ContextVar[str] = ContextVar("fe_last_stop_reason", default="")


def get_last_stop_reason() -> str:
    """
    Причина остановки последнего вызова модели в текущем потоке.

    "max_tokens" / "length" — ответ упёрся в потолок и оборван;
    "end_turn" / "stop"     — модель закончила сама;
    ""                      — провайдер не сообщил.
    """
    return _last_stop_reason.get()


def _remember_stop_reason(reason) -> None:
    _last_stop_reason.set(str(reason or ""))


def call_model(model_value: str, system: str, user: str,
               anthropic_key: str = None, nano_key: str = None,
               openai_key: str = None, gemini_key: str = None,
               deepseek_key: str = None,
               max_tokens: int = 4096,
               prefill: str = "",
               operation: str = "") -> str:
    """prefill — начало ответа модели (assistant prefill).
    Модель продолжает генерацию с этого текста, не может начать заново.
    Идеально для продолжения главы: передаём последние 200-300 слов."""
    provider, model_id = parse_model_value(model_value)
    _remember_stop_reason("")

    dispatch = {
        "anthropic_direct": (_call_anthropic,       anthropic_key),
        "openai_direct":    (_call_openai_direct,   openai_key),
        "gemini_direct":    (_call_gemini_direct,   gemini_key),
        "deepseek_direct":  (_call_deepseek_direct, deepseek_key),
        "nano_gpt":         (_call_nanogpt,         nano_key),
    }
    if provider not in dispatch:
        raise ValueError(f"Неизвестный провайдер: {provider}")
    fn, key = dispatch[provider]

    _remember_usage(0, 0)          # чтобы не записать расход прошлого вызова
    try:
        try:
            text = _reject_empty(fn(model_id, system, user, key, max_tokens, prefill),
                                 model_value, prefill)
        finally:
            # Запись в finally, а не после успеха: провайдер ответил —
            # значит вызов уже оплачен, даже если дальше упал разбор или
            # ответ оказался пустым. Поймано 22.09: пятнадцать вызовов
            # Sonnet 5 разбились о блок размышления, все были оплачены, и
            # в учёт не попал ни один — «потрачено $0» при непустом счёте.
            _record_usage(provider, model_id, operation)
        return text
    except Exception as exc:
        # Часть моделей (особенно из каталога nano-gpt) отдаёт меньше токенов,
        # чем просит пайплайн под полную главу. Такой отказ виден только по
        # тексту ошибки — единожды повторяем с уменьшенным потолком, вместо
        # того чтобы ронять генерацию целиком.
        retry = _reduced_max_tokens(exc, max_tokens)
        if retry is None:
            raise
        try:
            text = _reject_empty(fn(model_id, system, user, key, retry, prefill),
                                 model_value, prefill)
        finally:
            _record_usage(provider, model_id, operation)
        return text


# Расход последнего вызова: (input_tokens, output_tokens, цена провайдера).
# Тот же приём, что _remember_stop_reason — функции провайдеров возвращают
# только текст, а учёт нужен диспетчеру.
_LAST_USAGE: dict = {}


def _remember_usage(input_tokens: int, output_tokens: int,
                    reported_cost: float | None = None) -> None:
    _LAST_USAGE.clear()
    _LAST_USAGE.update({"input_tokens": int(input_tokens or 0),
                        "output_tokens": int(output_tokens or 0),
                        "reported_cost": reported_cost})


def get_last_usage() -> dict:
    """Расход последнего вызова. Пустой словарь — провайдер ничего не сообщил."""
    return dict(_LAST_USAGE)


def _record_usage(provider: str, model_id: str, operation: str = "") -> None:
    """
    Записать расход вызова в базу.

    Учёт — побочное дело: ни отсутствие токенов в ответе, ни отказ базы не
    должны ронять генерацию. Поэтому всё внутри try, а при пустом расходе
    запись не делается вовсе — строка с нулями только засоряла бы сводку.
    """
    try:
        u = get_last_usage()
        if not u or (not u.get("input_tokens") and not u.get("output_tokens")):
            return
        from .pricing import estimate_cost
        from .db_settings import record_api_usage
        cost = estimate_cost(provider, model_id, u["input_tokens"],
                             u["output_tokens"], u.get("reported_cost"))
        record_api_usage(provider, model_id, u["input_tokens"],
                         u["output_tokens"], cost, operation)
    except Exception:
        pass


def _reject_empty(text: str, model_value: str, prefill: str) -> str:
    """
    Пустой ответ модели — это отказ, а не текст.

    Замер 2026-09-13: z-ai/glm-5.3 примерно в половине вызовов отдаёт
    пустое содержимое с finish_reason='length' — бюджет израсходован, а
    в ответе ничего. Проверено, что это поведение провайдера, а не наше:
    сырой HTTP-запрос и вызов через SDK дают одну и ту же картину
    (0 · 0 · 666 символов против 0 · 822 · 116).

    Раньше такая пустота уходила наверх обычной строкой. run_generation
    её ловил, а шаг генерации в пайплайне, score_text и замер — нет:
    в историю сохранялась пустая итерация, а оценка выходила 0 из 50,
    неотличимая от «модель написала плохо».

    Проверка в диспетчере, а не в пяти функциях провайдеров: так её
    нельзя забыть при добавлении шестого.
    """
    body = (text or "")
    if prefill and body.startswith(prefill):
        body = body[len(prefill):]          # своё ли модель что-то добавила
    if body.strip():
        return text
    reason = get_last_stop_reason() or "причина не сообщена"
    raise ValueError(
        f"Модель {model_value} вернула пустой ответ (finish_reason={reason}). "
        f"Это отказ провайдера, а не текст главы."
    )


# Формулировки, которыми провайдеры сообщают именно о завышенном ПОТОЛКЕ ВЫВОДА.
_MAX_TOKEN_ERROR_MARKERS = (
    "max_tokens", "max tokens", "maximum tokens",
    "max_completion_tokens", "max output tokens", "output limit",
)

# Формулировки, при которых повторять бессмысленно или вредно.
_NO_RETRY_MARKERS = (
    "rate_limit", "rate limit", "429", "quota",
    "invalid_api_key", "authentication", "permission",
    "context length", "context_length", "context window",
)


def _reduced_max_tokens(exc: Exception, current: int) -> int | None:
    """
    Если ошибка — про слишком большой потолок ВЫВОДА, вернуть уменьшенное значение.
    Иначе None: ошибка не наша, пробрасываем как есть.

    Отдельно отсекаются лимиты запросов, проблемы с ключом и переполнение окна
    ВВОДА: повтор с меньшим max_tokens их не лечит, а лишний вызов стоит денег.
    """
    msg = str(exc).lower()
    if any(mark in msg for mark in _NO_RETRY_MARKERS):
        return None
    if not any(mark in msg for mark in _MAX_TOKEN_ERROR_MARKERS):
        return None
    reduced = max(4096, current // 2)
    return reduced if reduced < current else None


# ─── Клиенты ─────────────────────────────────────────────────────────────────

def _first_text_block(content) -> str:
    """
    Текст ответа — из первого блока, у которого он есть.

    Брали `content[0].text`. У думающих моделей (Sonnet 5, Opus 5 и далее)
    первым идёт блок размышления, и обращение к `.text` падает с
    AttributeError: 'ThinkingBlock' object has no attribute 'text'.
    Поймано 22.09 при переводе судьи на claude-sonnet-5: пятнадцать
    вызовов подряд отработали, были оплачены — и все разбились о разбор.

    Блоков размышления может не быть вовсе (Haiku 4.5), может быть один
    пустой (у Sonnet 5 их содержимое по умолчанию не возвращается), может
    быть несколько. Поэтому ищем первый текстовый, а не считаем позиции.
    """
    for block in content or []:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text:
            return text
    raise ValueError(
        "В ответе модели нет текстового блока: "
        f"{[getattr(b, 'type', type(b).__name__) for b in (content or [])]}"
    )


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
    _remember_stop_reason(getattr(msg, "stop_reason", ""))
    u = getattr(msg, "usage", None)
    _remember_usage(getattr(u, "input_tokens", 0), getattr(u, "output_tokens", 0))
    result = _first_text_block(msg.content)
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
    _remember_stop_reason(getattr(resp.choices[0], "finish_reason", ""))
    _u = getattr(resp, "usage", None)
    _remember_usage(getattr(_u, "prompt_tokens", 0), getattr(_u, "completion_tokens", 0),
                    getattr(_u, "cost", None))
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
    _remember_stop_reason(getattr(resp.choices[0], "finish_reason", ""))
    _u = getattr(resp, "usage", None)
    _remember_usage(getattr(_u, "prompt_tokens", 0), getattr(_u, "completion_tokens", 0),
                    getattr(_u, "cost", None))
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
    _remember_stop_reason(getattr(resp.choices[0], "finish_reason", ""))
    _u = getattr(resp, "usage", None)
    _remember_usage(getattr(_u, "prompt_tokens", 0), getattr(_u, "completion_tokens", 0),
                    getattr(_u, "cost", None))
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
    _remember_stop_reason(getattr(resp.choices[0], "finish_reason", ""))
    _u = getattr(resp, "usage", None)
    _remember_usage(getattr(_u, "prompt_tokens", 0), getattr(_u, "completion_tokens", 0),
                    getattr(_u, "cost", None))
    result = resp.choices[0].message.content
    return (prefill + result) if prefill else result
