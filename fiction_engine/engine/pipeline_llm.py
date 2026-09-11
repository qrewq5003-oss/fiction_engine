"""
pipeline_llm.py — доступ к модели и сборка системных промптов.

Выделено из pipeline.py: файл дорос до 858 строк и держал сразу три темы —
оркестрацию цикла, работу с моделью и отдельные операции над главой.
Публичный путь импорта не изменился: pipeline реэкспортирует всё, что
нужно снаружи.
"""

import re

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


def _make_model_caller(model_value: str, max_tokens: int = 400):
    """
    Вызыватель дешёвой модели для вспомогательных задач.

    max_tokens по умолчанию 400 — под короткую справку. Задачам, которые
    просят структурированный ответ, этого мало, и обрыв там неотличим от
    брака: ответ рвётся посреди строки, JSON перестаёт разбираться, автор
    видит «не удалось сгенерировать».

    Замер на живом прогоне 2026-09-12 (глава 3, 5 попыток подряд):
        400 токенов  → stop_reason='max_tokens', JSON битый,  5 отказов из 5
        1500 токенов → stop_reason='end_turn',   JSON целый,  0 отказов
    """
    caller_model = _get_resolver_model(model_value)
    def caller(prompt: str) -> str:
        return _call(caller_model, "Ты помощник писателя. Отвечай точно и кратко.",
                     prompt, max_tokens=max_tokens)
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


# Разметка, которой модель украшает ответ. Снимается ПЕРЕД разбором.
#
# Найдено настоящим прогоном 2026-09-12: в одном запуске одна и та же модель
# написала критику как «## ИТОГ: 24/50» (разобралось в 24) и вердикт как
# «**ИТОГ:** 24/50» — регулярка `ИТОГ:\s*(\d+)` требует цифру сразу после
# двоеточия, а там стояли звёздочки. В базу легло 0.0 при реальных 24.
#
# С вердиктом было опаснее: `**ВЕРДИКТ:** ПРИНЯТЬ` тоже не совпадал, а
# значение по умолчанию — «НА ДОРАБОТКУ». Принятая глава возвращалась
# автору на доработку, и он платил за новые итерации уже готового текста.
# В тестах этого не видно по построению: заглушка отдаёт строку, написанную
# под регулярку, а не то, что пишет живая модель.
_MARKUP = re.compile(r'[*_`#~]+')


def _plain(text: str) -> str:
    """Текст без markdown-украшений — для разбора чисел и вердиктов."""
    return _MARKUP.sub('', text or '')


def parse_score(text: str) -> float:
    plain = _plain(text)
    m = re.search(r'ИТОГ:\s*(\d+(?:\.\d+)?)', plain, re.IGNORECASE)
    if m:
        return float(m.group(1))
    scores = re.findall(r'(?:ГОЛОС|СТРУКТУРА|ПЕРСОНАЖИ|СЦЕНЫ|ДИАЛОГ):\s*(\d+)',
                        plain, re.IGNORECASE)
    return sum(float(s) for s in scores) if scores else 0.0


def parse_criterion(text: str, label: str) -> int:
    """Одна оценка по названию критерия. 0 — критерий не найден."""
    m = re.search(rf"{label}:\s*(\d+)", _plain(text), re.IGNORECASE)
    return int(m.group(1)) if m else 0


def parse_verdict(text: str) -> str:
    m = re.search(r'ВЕРДИКТ:\s*(ПРИНЯТЬ|НА ДОРАБОТКУ)', _plain(text), re.IGNORECASE)
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


def parse_json(raw: str):
    """Разобрать JSON-объект ИЛИ массив из ответа модели. None — не вышло."""
    return _parse_json_impl(raw)


def _parse_json_impl(raw: str):
    """
    Разобрать JSON из ответа модели. None — не удалось ничем.

    Разбор отделён от вызова модели намеренно: та же терпимость нужна
    везде, где модель просят вернуть структуру, а не только в call_json.
    L3-память держала рядом свою упрощённую версию (`{.*}` жадно, от
    первой скобки до последней) — на обрезанном ответе она отдавала
    огрызок, json.loads падал, и автор получал «не удалось сгенерировать
    саммари» вместо «ответ не поместился в лимит».
    """
    import json

    if not isinstance(raw, str) or not raw.strip():
        return None

    # 1. Прямой разбор
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass

    # 2. Убрать <think>...</think> (DeepSeek R1) и markdown-обрамление
    raw_no_think = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
    cleaned = re.sub(r'```(?:json)?\s*', '', raw_no_think).strip().rstrip('`').strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 3. Найти JSON по балансу скобок (устойчиво к тексту вокруг).
    #    Массив верхнего уровня тоже бывает ответом — narrative_intelligence
    #    просит именно список, и объектная выемка его теряла.
    #    Порядок важен: в `[{"a": 1}]` объектная выемка нашла бы внутренний
    #    объект и вернула его вместо массива. Берём ту скобку, что в тексте
    #    встретилась раньше.
    pairs = sorted((('{', '}'), ('[', ']')),
                   key=lambda p: (raw.find(p[0]) if p[0] in raw else len(raw) + 1))
    for opener, closer in pairs:
        found = _scan_balanced(raw, opener, closer)
        if found is not None:
            return found

    return None


def _scan_balanced(raw: str, opener: str, closer: str):
    import json
    start = raw.find(opener)
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
                if ch == opener: depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        end = i + 1; break
        if end != -1:
            try:
                return json.loads(raw[start:end])
            except json.JSONDecodeError:
                pass
    return None


def call_json(model_value: str, system: str, prompt: str,
              max_tokens: int = 2000) -> dict:
    raw = _call(model_value, system, prompt, max_tokens=max_tokens)
    data = parse_json(raw)
    if data is None:
        raise ValueError(f"Модель не вернула корректный JSON. Ответ: {raw[:300]}")
    return data
