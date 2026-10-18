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
    # Только при FE_CLAUDE_SUBSCRIPTION=1 — см. _call_claude_subscription
    "claude_subscription": {
        "label": "Claude (подписка, личное)",
        "models": [
            # Точные имена, а не алиасы sonnet/opus/haiku: алиас сам переезжает
            # на новую версию, и замеры перестают быть сравнимы. Fable 5.1 в
            # подписку не входит («requires usage credits», 08.10).
            {"id": "claude-sonnet-5-5",         "name": "Claude Sonnet 5.5 — через подписку Claude Code"},
            {"id": "claude-opus-5-5",           "name": "Claude Opus 5.5 — через подписку Claude Code"},
            {"id": "claude-haiku-5-5",          "name": "Claude Haiku 5.5 — через подписку Claude Code"},
        ]
    },
    # Только при FE_CHATGPT_SUBSCRIPTION=1 — см. _call_chatgpt_subscription.
    # После @ — глубина размышления (low, medium, high, xhigh, max)
    "chatgpt_subscription": {
        "label": "GPT (подписка ChatGPT, личное)",
        "models": [
            # Замер 15.10 (bench/ab-writers-gpt61-2026-10-15.json): лучше DeepSeek,
            # почти вровень с Sonnet; ≈3 % окна 5 часов Plus на главу
            {"id": "gpt-6.1-sol@medium",  "name": "GPT-6.1 Sol ★ через подписку ChatGPT (Codex) — сильнее DeepSeek, вровень с Sonnet"},
            {"id": "gpt-6-astra@medium",  "name": "GPT-6 Astra — через подписку ChatGPT (Codex)"},
            {"id": "gpt-6-luna@medium",   "name": "GPT-6 Luna — через подписку ChatGPT (Codex)"},
        ]
    },
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
        if provider_key == "claude_subscription" and not claude_subscription_enabled():
            continue
        if provider_key == "chatgpt_subscription" and not chatgpt_subscription_enabled():
            continue
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
        "claude_subscription": (_call_claude_subscription, None),
        "chatgpt_subscription": (_call_chatgpt_subscription, None),
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


# Метка текущего шага для учёта расходов. Через контекст, а не аргументом
# call_model: шаговые функции зовут call_fn, который подменяется в тестах
# заглушками с фиксированной сигнатурой — лишний параметр их ломает.
_CURRENT_OPERATION = {"name": ""}


def set_current_operation(name: str) -> None:
    _CURRENT_OPERATION["name"] = name or ""


def get_current_operation() -> str:
    return _CURRENT_OPERATION["name"]


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
        operation = operation or get_current_operation()
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

# Модели, у которых есть параметр thinking. На более старых (Haiku 4.5 и
# ранее) его передача — ошибка запроса, поэтому проверяем перед отправкой.
_THINKING_MODELS = ("claude-sonnet-5", "claude-opus-5", "claude-opus-4-",
                    "claude-fable-", "claude-mythos-", "claude-sonnet-4-6")


def _supports_thinking(model_id: str) -> bool:
    return any(model_id.startswith(p) for p in _THINKING_MODELS)


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
    # Размышление выключено явно.
    #
    # На моделях 5-го поколения (Sonnet 5, Opus 5) оно включено ПО
    # УМОЛЧАНИЮ, когда параметр не передан. Все бюджеты max_tokens в этом
    # движке подобраны под модели без размышления: критику даётся 1200
    # токенов, судье 2000. Размышление съедает тот же бюджет — и до ответа
    # не доходит ничего.
    #
    # Поймано 22.09 при переводе судьи на claude-sonnet-5: из 15 вызовов 8
    # вернули ответ вообще без текстового блока, остальные — обрубок, где
    # оценки разбирались в нули. Средний выход упёрся в потолок: 1145 из
    # 1200. Двадцать два вызова и $0.53 ушли на мусор.
    #
    # Задача критика и судьи — разметить текст по готовой рубрике, а не
    # рассуждать. Если размышление понадобится, включать его надо вместе с
    # поднятым бюджетом, иначе повторится то же самое.
    kwargs = dict(model=model_id, max_tokens=max_tokens,
                  system=system, messages=messages)
    if _supports_thinking(model_id):
        kwargs["thinking"] = {"type": "disabled"}
    msg = client.messages.create(**kwargs)
    _remember_stop_reason(getattr(msg, "stop_reason", ""))
    u = getattr(msg, "usage", None)
    _remember_usage(getattr(u, "input_tokens", 0), getattr(u, "output_tokens", 0))
    result = _first_text_block(msg.content)
    return (prefill + result) if prefill else result


# ─── Claude через подписку Claude Code ───────────────────────────────────────
#
# Вызов идёт через установленный и залогиненный `claude` CLI в режиме -p:
# расход списывается с подписки Pro/Max, а не с ключа API. Только для
# личного использования и выключено по умолчанию (FE_CLAUDE_SUBSCRIPTION=1).
#
# Риски — на владельце аккаунта: условия Anthropic рассчитаны на подписку в
# приложениях Anthropic и Claude Code, сторонние инструменты — через ключи
# API; аккаунт могут ограничить. Лимит подписки общий с Claude Code. Поэтому
# вызовы строго по одному, а для замеров и пакетной работы этот провайдер
# не годится — для них ключ API (anthropic_direct).
#
# Ограничения CLI: нет temperature; prefill эмулируется просьбой продолжить
# с места; каждый вызов — отдельный процесс (медленнее API на секунды).

import shutil
import subprocess
import threading

_CLAUDE_SUB_LOCK = threading.Lock()
CLAUDE_SUB_TIMEOUT = 900          # секунд: длинная глава пишется минутами
CLAUDE_SUB_MIN_OUTPUT = 32000      # токенов: глава в 3–4 тыс. слов — около 12 тыс.


def claude_subscription_enabled() -> bool:
    return os.environ.get("FE_CLAUDE_SUBSCRIPTION") == "1" and bool(shutil.which("claude"))


def _parse_claude_stream(stdout: str) -> tuple[str, dict | None]:
    """
    Вывод `claude -p --output-format stream-json`: текст всех сообщений модели
    подряд (продолжения после лимита вывода — с того же места, без
    разделителя) и итоговое событие result. Итога нет — (текст, None).
    Старый вывод одним JSON (--output-format json) тоже разбирается.
    """
    import json as _json
    parts: list[str] = []
    final: dict | None = None
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = _json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "assistant":
            parts += [b.get("text") or "" for b in (ev.get("message") or {}).get("content") or []
                      if isinstance(b, dict) and b.get("type") == "text"]
        elif ev.get("type") == "result" or ("result" in ev and "is_error" in ev):
            final = ev
    text = "".join(parts)
    if final is not None and not parts and not final.get("is_error"):
        text = final.get("result") or ""          # одним JSON: текста в потоке нет
    return text, final


def _call_claude_subscription(model_id, system, user, api_key, max_tokens, prefill=""):
    if not claude_subscription_enabled():
        raise ValueError("Claude через подписку выключен: нужен FE_CLAUDE_SUBSCRIPTION=1 "
                         "и залогиненный `claude` CLI")
    prompt = user
    if prefill:
        prompt = (user + "\n\nТекст ниже оборван. Верни ТОЛЬКО его продолжение — со "
                  "следующего слова, без повтора написанного и без пояснений.\n\n"
                  "=== УЖЕ НАПИСАНО ===\n" + prefill)
    # Полный путь: на Windows `claude` — это claude.cmd (npm), а subprocess
    # без shell находит только .exe
    # stream-json, а не json: упёршись в CLAUDE_CODE_MAX_OUTPUT_TOKENS, CLI сам
    # просит модель продолжить новым сообщением («Output token limit hit.
    # Resume directly…»), а в итоговом result отдаёт только последнее. Глава
    # теряла начало и открывалась обрывком слова («ень.») — 7 из 98 глав
    # Sonnet в замерах, 15.10 у автора. Поток содержит все сообщения модели.
    cmd = [shutil.which("claude") or "claude", "-p", "--model", model_id, "--system-prompt", system or "",
           "--tools", "", "--output-format", "stream-json", "--verbose", "--no-session-persistence",
           "--setting-sources", "", "--strict-mcp-config"]
    # Лимит вывода — не меньше CLAUDE_SUB_MIN_OUTPUT: по нему CLI режет ответ и
    # просит продолжить, а на стыке продолжения слова слипаются или рвутся.
    # Подписка за токены не берёт, длину главы задаёт промпт
    env = dict(os.environ, CLAUDE_CODE_MAX_OUTPUT_TOKENS=str(max(max_tokens or 0, CLAUDE_SUB_MIN_OUTPUT)),
               MAX_THINKING_TOKENS="0")       # размышление съедает бюджет ответа (см. _call_anthropic)
    # Долгоживущий токен `claude setup-token`: из настроек приложения, иначе из
    # окружения; без него CLI берёт свой `claude login`
    from .db_settings import get_api_key
    token = get_api_key("claude_subscription")
    if token and token != "claude-cli":
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    with _CLAUDE_SUB_LOCK:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=CLAUDE_SUB_TIMEOUT, env=env)
    result, data = _parse_claude_stream(proc.stdout)
    if data is None:
        raise RuntimeError(f"claude CLI: нет итога (код {proc.returncode}): "
                           f"{(proc.stderr or proc.stdout)[:300]}")
    # Продолжения кончились, а лимит вывода снова исчерпан: написанное не
    # выбрасываем — это обрыв, его дописывает «Продолжить главу»
    cut = data.get("api_error") == "max_output_tokens" and bool(result.strip())
    if data.get("is_error") and not cut:
        raise RuntimeError(f"claude CLI: {str(data.get('result') or data)[:300]}")
    reason = "max_tokens" if cut else (data.get("stop_reason") or "")
    _remember_stop_reason("max_tokens" if reason in ("max_tokens", "length") else reason)
    u = data.get("usage") or {}
    # Подписка не тарифицирует токены — стоимость 0, чтобы сводка расходов не врала
    _remember_usage(int(u.get("input_tokens", 0)) + int(u.get("cache_read_input_tokens", 0))
                    + int(u.get("cache_creation_input_tokens", 0)),
                    int(u.get("output_tokens", 0)), 0.0)
    if not prefill:
        return result
    # Стык: модель отдаёт продолжение без пробела в начале
    glue = "" if (not result or prefill[-1:].isspace() or result[:1].isspace()
                  or result[:1] in ",.;:!?…»)") else " "
    return prefill + glue + result


# ─── GPT через подписку ChatGPT (Codex CLI) ──────────────────────────────────
#
# То же, что Claude через подписку, но через `codex exec`: расход — с подписки
# ChatGPT Plus/Pro, вход — `codex login`. Выключено по умолчанию
# (FE_CHATGPT_SUBSCRIPTION=1), риски условий те же, лимит общий с Codex.
#
# Codex — агент с инструментами. Поэтому: пустая временная папка, песочница
# read-only, инструменты выключены, свой файл инструкций вместо агентских
# (служебный промпт с 13.8 тыс. токенов падает до 7.6 тыс.), без чужого
# config.toml и правил, сессия не сохраняется. Если модель всё же вызвала
# инструмент — ошибка, а не ответ.
#
# Нет temperature и потолка ответа (max_tokens не передаётся); prefill — как
# у Claude CLI, просьбой продолжить.

_CHATGPT_SUB_LOCK = threading.Lock()
CHATGPT_SUB_TIMEOUT = 900
_CODEX_OFF = ("shell_tool", "unified_exec", "apps", "plugins", "view_image", "image_generation",
              "browser_use", "computer_use", "in_app_browser", "multi_agent", "goals",
              "skill_search", "tool_suggest", "sleep_tool", "hooks")


def chatgpt_subscription_enabled() -> bool:
    return os.environ.get("FE_CHATGPT_SUBSCRIPTION") == "1" and bool(shutil.which("codex"))


def _codex_cmd() -> list[str]:
    # npm ставит на Windows codex.cmd; через cmd.exe аргументы с кавычками и
    # путями ломаются, поэтому — node и codex.js напрямую, если они рядом
    exe = shutil.which("codex") or "codex"
    js = os.path.join(os.path.dirname(exe), "node_modules", "@openai", "codex", "bin", "codex.js")
    if exe.lower().endswith(".cmd") and os.path.exists(js):
        return [shutil.which("node") or "node", js]
    return [exe]


def _call_chatgpt_subscription(model_id, system, user, api_key, max_tokens, prefill=""):
    import json as _json
    import tempfile
    if not chatgpt_subscription_enabled():
        raise ValueError("GPT через подписку выключен: нужен FE_CHATGPT_SUBSCRIPTION=1 "
                         "и залогиненный `codex` CLI")
    model, _, effort = model_id.partition("@")
    prompt = user
    if prefill:
        prompt = (user + "\n\nТекст ниже оборван. Верни ТОЛЬКО его продолжение — со "
                  "следующего слова, без повтора написанного и без пояснений.\n\n"
                  "=== УЖЕ НАПИСАНО ===\n" + prefill)
    with tempfile.TemporaryDirectory(prefix="fe-codex-") as tmp:
        work = os.path.join(tmp, "work")
        os.mkdir(work)
        instr = os.path.join(tmp, "instructions.md").replace("\\", "/")
        with open(instr, "w", encoding="utf-8") as f:
            f.write((system or "") + "\n\nОтвечай только текстом. Инструментов нет.")
        last = os.path.join(tmp, "last.txt")
        cmd = _codex_cmd() + [
            "exec", "--json", "--ephemeral", "--skip-git-repo-check", "--ignore-user-config",
            "--ignore-rules", "-s", "read-only", "-C", work, "-m", model, "-o", last,
            "-c", f"model_instructions_file='{instr}'"]
        if effort:
            cmd += ["-c", f"model_reasoning_effort={effort}"]
        for feat in _CODEX_OFF:
            cmd += ["--disable", feat]
        cmd.append("-")
        with _CHATGPT_SUB_LOCK:
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  timeout=CHATGPT_SUB_TIMEOUT)
        # --json пишет по событию в строку; прочие строки (предупреждения CLI) — не события
        events = [_json.loads(line) for line in (proc.stdout or "").splitlines()
                  if line.startswith("{") and line.rstrip().endswith("}")]
        result = ""
        if os.path.exists(last):
            with open(last, encoding="utf-8") as f:
                result = f.read()
    tools = [e["item"].get("type") for e in events if e.get("type", "").startswith("item.")
             and e.get("item", {}).get("type") not in ("agent_message", "reasoning", "error")]
    # item «error» — не инструмент: так codex тоже сообщает о переподключении
    errors = [str(e.get("message") or e.get("error") or e) for e in events
              if e.get("type") in ("error", "turn.failed")]
    # Событие error бывает и промежуточным: «Reconnecting... 2/5 (tls handshake
    # eof)» — codex переподключается сам и доводит ход до turn.completed. Такой
    # ответ раньше выбрасывался как ошибка (18.10: обрыв на каждом втором
    # вызове Sol, повторы тратили подписку). Ошибка — только если ход не дошёл
    completed = any(e.get("type") == "turn.completed" for e in events)
    failed = any(e.get("type") == "turn.failed" for e in events)
    if completed and not failed and not proc.returncode and result.strip():
        errors = []
    if errors or proc.returncode:
        raise RuntimeError(f"codex: {(errors[-1] if errors else (proc.stderr or proc.stdout))[:300]}")
    if tools:
        raise RuntimeError(f"codex: модель вызвала инструмент ({', '.join(dict.fromkeys(tools))})")
    u = next((e.get("usage") or {} for e in reversed(events) if e.get("type") == "turn.completed"), {})
    _remember_stop_reason("stop")
    _remember_usage(int(u.get("input_tokens", 0)), int(u.get("output_tokens", 0)), 0.0)
    if not prefill:
        return result
    glue = "" if (not result or prefill[-1:].isspace() or result[:1].isspace()
                  or result[:1] in ",.;:!?…»)") else " "
    return prefill + glue + result


def chatgpt_limits() -> dict:
    """Остаток лимитов подписки ChatGPT: {"primary": {...}, "secondary": {...}, "plan": ...}.
    Окна — 5 часов и неделя, usedPercent — сколько израсходовано, resetsAt — unix-время.
    Читается у `codex app-server` (account/rateLimits/read); вызова модели нет."""
    import json as _json
    p = subprocess.Popen(_codex_cmd() + ["app-server"], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         text=True, encoding="utf-8")
    try:
        def rpc(i, method, params):
            p.stdin.write(_json.dumps({"jsonrpc": "2.0", "id": i, "method": method,
                                       "params": params}) + "\n")
            p.stdin.flush()
            for line in p.stdout:
                m = _json.loads(line)
                if m.get("id") == i:
                    return m
            raise RuntimeError("codex app-server закрылся")
        rpc(1, "initialize", {"clientInfo": {"name": "fiction-engine", "version": "1"}})
        p.stdin.write(_json.dumps({"jsonrpc": "2.0", "method": "initialized"}) + "\n")
        snap = (rpc(2, "account/rateLimits/read", {}).get("result") or {}).get("rateLimits") or {}
    finally:
        p.kill()
    return {"primary": snap.get("primary"), "secondary": snap.get("secondary"),
            "plan": snap.get("planType"), "reached": snap.get("rateLimitReachedType")}


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
