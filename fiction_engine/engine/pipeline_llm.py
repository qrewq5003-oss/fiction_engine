"""
pipeline_llm.py — доступ к модели и сборка системных промптов.

Выделено из pipeline.py: файл дорос до 858 строк и держал сразу три темы —
оркестрацию цикла, работу с моделью и отдельные операции над главой.
Публичный путь импорта не изменился: pipeline реэкспортирует всё, что
нужно снаружи.
"""

from .error_policy import (handle_error, ErrorLevel)
from .pipeline_context import build_context


# ─── Проксирование через pipeline ─────────────────────────────────────────────
# См. pipeline_tasks: имя разрешается при вызове, чтобы подмена
# engine.pipeline._call в тестах продолжала действовать.

def _call(*args, **kwargs):
    from . import pipeline
    return pipeline._call(*args, **kwargs)


def _get_resolver_model(fallback_model: str) -> str:
    try:
        from .db import get_conn
        with get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key='resolver_model'"
            ).fetchone()
        if row and row["value"]:
            return row["value"]
    except Exception as e:
        handle_error("_get_resolver_model", e, level=ErrorLevel.RECOVERABLE)
    return fallback_model


def _make_module_resolver(model_value: str):
    resolver_model = _get_resolver_model(model_value)
    def api_call_fn(prompt: str) -> str:
        return _call(resolver_model,
                     "Ты помощник писателя. Отвечай только валидным JSON без пояснений.",
                     prompt, max_tokens=200)
    return api_call_fn


def _make_model_caller(model_value: str):
    caller_model = _get_resolver_model(model_value)
    def caller(prompt: str) -> str:
        return _call(caller_model, "Ты помощник писателя. Отвечай точно и кратко.",
                     prompt, max_tokens=400)
    return caller


def _build_sys_generator(genre_text: str = "") -> str:
    try:
        from .unified_engine import detect_genre
        genre_key    = detect_genre(genre_text) if genre_text else None
        genre_family = genre_key.split("_")[0] if genre_key else None
    except Exception as e:
        handle_error("_build_sys_generator", e, level=ErrorLevel.RECOVERABLE)
        genre_family = None

    identity_map = {
        "fantasy":   "автор коммерческого фэнтези",
        "detective": "автор детективной прозы",
        "thriller":  "автор психологического триллера",
        "horror":    "автор хоррора",
        "scifi":     "автор научной фантастики",
        "romance":   "автор романтической прозы",
        "realism":   "автор реалистической прозы",
    }
    identity = identity_map.get(genre_family, "профессиональный автор коммерческой прозы")
    return (
        f"Ты — {identity} на русском языке.\n"
        "Пишешь художественный текст высокого качества. Строго следуешь инструкциям промпта.\n"
        "ТРЕБОВАНИЕ К ОБЪЁМУ: глава должна быть 2500-3000 слов. "
        "Если глава короче 2000 слов — это провал задания. Пиши полные развёрнутые сцены.\n"
        "ЗАПРЕЩЕНО АБСОЛЮТНО: длинное тире (—) в авторской речи, описаниях, ремарках. "
        "Длинное тире допустимо ТОЛЬКО внутри прямой речи персонажей для обозначения реплики. "
        "В авторском тексте используй запятые, точки, двоеточия — но не тире.\n"
        "Возвращаешь только текст главы — без заголовков, комментариев и пояснений."
    )


def parse_score(text: str) -> float:
    import re
    m = re.search(r'ИТОГ:\s*(\d+(?:\.\d+)?)', text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    scores = re.findall(r'(?:ГОЛОС|СТРУКТУРА|ПЕРСОНАЖИ|СЦЕНЫ|ДИАЛОГ):\s*(\d+)', text, re.IGNORECASE)
    return sum(float(s) for s in scores) if scores else 0.0


def parse_verdict(text: str) -> str:
    import re
    m = re.search(r'ВЕРДИКТ:\s*(ПРИНЯТЬ|НА ДОРАБОТКУ)', text, re.IGNORECASE)
    return m.group(1).upper() if m else "НА ДОРАБОТКУ"


def _build_context(project_id: int, chapter_num: int, base_prompt: str,
                   mode: str = "quick", model_value: str = "",
                   task_text: str = "") -> str:
    """Обёртка для обратной совместимости."""
    api_call_fn = _make_module_resolver(model_value) if mode == "master" else None
    return build_context(project_id, chapter_num, base_prompt,
                         mode, model_value, task_text, api_call_fn)


def _build_consolidated_voice(active_voice, last_chapters, mode):
    from .pipeline_context import build_consolidated_voice
    return build_consolidated_voice(active_voice, last_chapters, mode)


def _extract_relevant_state(state, prompt_text):
    from .pipeline_context import extract_relevant_state
    return extract_relevant_state(state, prompt_text)


def call_json(model_value: str, system: str, prompt: str,
              max_tokens: int = 2000) -> dict:
    import json, re

    raw = _call(model_value, system, prompt, max_tokens=max_tokens)

    # 1. Прямой парсинг
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass

    # 2. Убрать <think>...</think> (DeepSeek R1)
    raw_no_think = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
    # Убрать markdown-блоки
    cleaned = re.sub(r'```(?:json)?\s*', '', raw_no_think).strip().rstrip('`').strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 3. Найти JSON по балансу скобок (устойчиво к тексту вокруг)
    start = raw.find('{')
    if start != -1:
        depth, end, in_str, escape = 0, -1, False, False
        for i, ch in enumerate(raw[start:], start):
            if escape:
                escape = False; continue
            if ch == '\\' and in_str:
                escape = True; continue
            if ch == '"':
                in_str = not in_str; continue
            if not in_str:
                if ch == '{': depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1; break
        if end != -1:
            try:
                return json.loads(raw[start:end])
            except json.JSONDecodeError:
                pass

    raise ValueError(f"Модель не вернула корректный JSON. Ответ: {raw[:300]}")
