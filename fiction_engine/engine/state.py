"""
state.py — State Engine: анализ глав и CRUD.

Сборка промптов для генерации вынесена в state_prompts.py.
"""

from .db import get_l3_summaries
from .l3_memory import normalize_promises, get_active_promises
from .api import call_model
from .db import (get_state, get_chapter, save_state_update, get_api_key)


SYSTEM_ANALYZER = """Ты — редактор серии. Анализируешь главу и возвращаешь только изменения в State Engine.
Отвечай строго в указанном формате. Без вступлений, без пересказа, только изменения."""


def analyze_chapter(project_id: int, chapter_num: int, model_value: str) -> dict:
    """
    Анализировать главу через API, вернуть сырой анализ и сохранить в БД.
    Возвращает: {"update_id": int, "analysis": str, "next_context": str}
    """
    ch = get_chapter(project_id, chapter_num)
    if not ch:
        raise ValueError(f"Глава {chapter_num} не найдена")

    state = get_state(project_id)

    # Загружаем активные promises чтобы модель могла отметить закрытые
    try:
        from .cognitive_memory import get_weighted_promises
        from .l3_memory import normalize_promises, get_active_promises
        from .db import get_l3_summaries
        summaries = get_l3_summaries(project_id, chapter_num, n=20)
        active_promises: list[dict] = []
        for s in summaries:
            ch_num   = s["chapter_num"]
            promises = normalize_promises(s.get("promises", []), ch_num)
            active_promises.extend(get_active_promises(promises))
    except Exception:
        active_promises = []

    user_prompt = _build_analysis_prompt(chapter_num, state, ch["content"], active_promises)

    anthropic_key = get_api_key("anthropic_direct")
    nano_key = get_api_key("nano_gpt")

    analysis = call_model(
        model_value, SYSTEM_ANALYZER, user_prompt,
        anthropic_key=anthropic_key, nano_key=nano_key,
        max_tokens=4096
    )

    update_id = save_state_update(project_id, chapter_num, analysis)
    next_context = _extract_next_context(analysis)

    return {
        "update_id": update_id,
        "analysis": analysis,
        "next_context": next_context,
        "chapter_num": chapter_num,
    }


def _extract_next_context(analysis: str) -> str:
    """
    Извлечь блок контекста для следующей главы.
    Поддерживает JSON-формат (новый) и legacy text-формат (обратная совместимость).
    """
    import json, re
    # Пробуем JSON
    try:
        match = re.search(r'\{.*\}', analysis, re.DOTALL)
        if match:
            data = json.loads(match.group())
            ctx = data.get("next_context", "")
            if ctx:
                return ctx.strip()
    except (json.JSONDecodeError, AttributeError):
        # Ответ не в JSON — ниже пробуем текстовый разбор
        pass
    # Fallback: legacy формат
    marker = "=== КОНТЕКСТ ДЛЯ СЛЕДУЮЩЕЙ ГЛАВЫ ==="
    if marker in analysis:
        return analysis.split(marker)[-1].strip()
    return ""


def _build_analysis_prompt(
    chapter_num: int,
    state: dict,
    chapter_content: str,
    active_promises: list[dict] | None = None,
) -> str:
    """
    Строит промпт для анализа главы.

    active_promises — список активных сюжетных обещаний из cognitive_memory
    (формат: [{id, text}, ...]). Если передан — модель может указать какие
    закрыты в этой главе через поле resolved_promises.
    """
    # Блок активных обещаний — показываем модели что нужно отслеживать
    if active_promises:
        promise_lines = "\n".join(
            f"  [{p['id']}] {p['text']}" for p in active_promises
        )
        promises_block = f"\nАКТИВНЫЕ СЮЖЕТНЫЕ ОБЕЩАНИЯ (укажи id закрытых в resolved_promises):\n{promise_lines}\n"
    else:
        promises_block = ""

    return f"""ТЕКУЩИЙ STATE:

ПЕРСОНАЖИ:
{state['global_state']}

СЮЖЕТНЫЕ ЛИНИИ:
{state['plot_matrix']}

ПАМЯТЬ (кто что знает):
{state['memory_graph']}
{promises_block}
---

НОВАЯ ГЛАВА {chapter_num}:
{chapter_content}

---

Верни ТОЛЬКО валидный JSON без markdown-обёртки и без пояснений:
{{
  "global_state_changes": [
    {{
      "name": "Имя персонажа",
      "состояние": "новое состояние (или пусто если не изменилось)",
      "локация": "новая локация (или пусто)",
      "цель": "новая цель (или пусто)",
      "узнал": "что узнал в этой главе (или пусто)",
      "перестал_знать": "что оказалось ложью (или пусто)"
    }}
  ],
  "plot_changes": {{
    "следующий_шаг": "что логично произойдёт дальше",
    "статус": "активна | приостановлена | завершена",
    "новые_линии": ["название новой линии"],
    "закрытые_линии": ["название закрытой линии"]
  }},
  "memory_changes": [
    {{
      "name": "Имя",
      "knows": ["новый факт 1", "новый факт 2"],
      "no_longer_knows": ["факт который оказался ложью"]
    }}
  ],
  "world_moment": "текущий момент мира одним предложением (или пусто)",
  "open_questions": ["открытый вопрос после главы"],
  "next_context": "2-3 предложения: где все находятся, что произошло, какое нерешённое напряжение",
  "resolved_promises": ["id_закрытого_обещания"]
}}

ПРАВИЛА:
- Только реальные изменения. Пустая строка если поле не изменилось.
- global_state_changes: только персонажи у которых что-то изменилось.
- next_context: обязательно, это ключевой блок для следующей генерации.
- resolved_promises: список id обещаний которые получили payoff в этой главе. Пустой список [] если ни одно не закрыто."""


# ─── Обратная совместимость ───────────────────────────────────────────────────
# build_prompt и утилиты промптов реэкспортируются из state_prompts.py

from .state_prompts import (  # noqa: E402, F401
    build_prompt,
    strip_empty_placeholders,
    _build_char_prefill,
    _cliche_block,
    _genre_identity,
    _genre_rules,
    _director_block,
)


# ─── Авто-очередь State Engine из pipeline ────────────────────────────────────

def queue_state_update_from_analysis(
    project_id: int,
    chapter_num: int,
    chapter_text: str,
    call_fn,                  # fn(prompt: str) -> str — дешёвая модель
) -> bool:
    """
    Запускает analyze_chapter() фоново и складывает результат в очередь
    state_updates как pending update (пользователь применяет одним кликом).

    Вызывается из step_chapter_analysis() после успешного сохранения ChapterAnalysis.
    Использует дешёвую модель — не блокирует основной pipeline.

    Возвращает True если update успешно поставлен в очередь, False при любой ошибке.
    Никогда не бросает исключений — RECOVERABLE по контракту.
    """
    try:
        if not chapter_text or len(chapter_text.strip()) < 100:
            return False

        state = get_state(project_id)

        # Загружаем активные promises — передаём в промпт
        try:
            summaries = get_l3_summaries(project_id, chapter_num, n=20)
            active_promises: list[dict] = []
            for s in summaries:
                ch_num   = s["chapter_num"]
                promises = normalize_promises(s.get("promises", []), ch_num)
                active_promises.extend(get_active_promises(promises))
        except Exception:
            active_promises = []

        prompt = _build_analysis_prompt(chapter_num, state, chapter_text, active_promises)

        analysis_text = call_fn(prompt)
        if not analysis_text or len(analysis_text.strip()) < 20:
            return False

        save_state_update(project_id, chapter_num, analysis_text)
        return True

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"queue_state_update_from_analysis failed (project={project_id}, "
            f"ch={chapter_num}): {e}"
        )
        return False
