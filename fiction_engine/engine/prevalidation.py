"""
Пре-валидация задачи главы (#7).
Проверяет задачу ДО генерации — нет ли противоречий с State Engine
и не нарушает ли она активные сюжетные обещания из L3 памяти.
"""

from .api import call_model
from .db import get_api_key, get_state, get_chapter, get_prep, log_error, check_structural_monotony
from .logger import get_logger
from .cognitive_memory import get_weighted_promises  # когнитивная память — Шаг 3

log = get_logger(__name__)

SYS_VALIDATOR = """Ты — редактор-консультант детективного агентства по нарративным ошибкам.
Проверяешь задачу главы на противоречия с известным состоянием серии.
Отвечай ТОЛЬКО в указанном JSON формате. Без пояснений вне JSON."""

VALIDATION_PROMPT = """Проверь задачу главы на противоречия и проблемы.

ТЕКУЩЕЕ СОСТОЯНИЕ СЕРИИ:
{state}

ПОДГОТОВКА (персонажи, мир):
{prep}

АКТИВНЫЕ СЮЖЕТНЫЕ ОБЕЩАНИЯ (promises из L3):
{promises}

ЗАДАЧА ГЛАВЫ {chapter_num}:
{task}

Верни JSON и только JSON:
{{
  "ok": true/false,
  "blocking": [
    {{
      "issue": "краткое описание проблемы",
      "detail": "конкретно что противоречит или отсутствует",
      "fix": "как исправить задачу"
    }}
  ],
  "warnings": [
    {{
      "issue": "некритичное замечание",
      "detail": "подробнее"
    }}
  ],
  "suggestions": ["необязательные улучшения — 1-2 строки каждое"]
}}

Блокирующие проблемы (blocking):
- Персонаж в задаче мёртв или не может быть в этой сцене согласно State Engine
- Событие противоречит уже установленным фактам
- Персонаж знает то чего знать не должен (информационная дыра)
- Локация недоступна по текущему состоянию
- Задача нарушает активное сюжетное обещание (promises) без его закрытия

Предупреждения (warnings):
- Персонаж действует вопреки своей диалектике без объяснения
- Темп не соответствует позиции в арке
- Пропущена подготовка для важного поворота
- Сюжетное обещание висит слишком долго без разрешения

Если задача корректна — ok: true, blocking: [], warnings: []
"""


def prevalidate_chapter(
    project_id: int,
    chapter_num: int,
    task: str,
    model_value: str,
) -> dict:
    """
    Проверить задачу главы перед генерацией.
    Возвращает dict с ok, blocking, warnings, suggestions.

    Три уровня проверки:
    1. Основной валидатор — state + prep + L3 promises в одном промпте
    2. Быстрая проверка противоречий State (вторая LLM-задача, дешёвая модель)
    3. Проверка promises — уже включена в основной промпт (без отдельного вызова)
    """
    state = get_state(project_id)
    prep  = get_prep(project_id)

    state_text = (
        f"ПЕРСОНАЖИ:\n{state.get('global_state', '')[:800]}\n\n"
        f"ЛИНИИ:\n{state.get('plot_matrix', '')[:400]}"
    )

    prep_parts = []
    from .db import PREP_SECTIONS, PREP_DEFAULTS
    for section, label in PREP_SECTIONS.items():
        content = prep.get(section, "").strip()
        if content and content != PREP_DEFAULTS.get(section, "").strip():
            prep_parts.append(f"{label}: {content[:300]}")
    prep_text = "\n".join(prep_parts) if prep_parts else "Не заполнено"

    # ─── Шаг 3: Получить активные promises из L3 memory ─────────────────────
    # Это ключевое соединение l3_memory ↔ prevalidation.
    # Promises из предыдущих глав теперь явно проверяются в промпте валидатора.
    promises_text = get_weighted_promises(project_id, before_chapter=chapter_num, n=10)
    if not promises_text:
        promises_text = "Нет активных обещаний (первые главы или саммари не сгенерированы)"

    prompt = VALIDATION_PROMPT.format(
        state=state_text,
        prep=prep_text,
        promises=promises_text,
        chapter_num=chapter_num,
        task=task,
    )

    keys = _get_api_keys()
    raw = call_model(model_value, SYS_VALIDATOR, prompt, max_tokens=1200, **keys)

    import json
    import re
    clean = re.sub(r"```json|```", "", raw).strip()
    try:
        result = json.loads(clean)
    except json.JSONDecodeError as e:
        log.error("prevalidate_chapter JSON parse", exc=e, project_id=project_id, chapter_num=chapter_num)
        result = {"ok": True, "blocking": [], "warnings": [], "suggestions": [], "_raw": raw}

    # ─── Проверка структурных паттернов (монотонность) ───────────────────────
    # Не LLM-вызов — статистика по БД. Быстро и бесплатно.
    monotony = check_structural_monotony(project_id, before_chapter=chapter_num)
    if monotony:
        result.setdefault("warnings", [])
        result["warnings"].append({"issue": "Структурная монотонность", "detail": monotony})

    # ─── Быстрая проверка противоречий State (отдельный дешёвый вызов) ──────
    # Остаётся как второй уровень — ловит то что основной мог пропустить.
    # Не дублирует promises (они уже в основном промпте).
    try:
        contradiction = _check_state_contradictions(
            project_id, chapter_num, task, model_value, state
        )
        if contradiction:
            result.setdefault("blocking", [])
            result["blocking"] = contradiction + result["blocking"]
            result["ok"] = False
    except Exception as e:
        log.error("prevalidate_chapter contradiction check", exc=e, project_id=project_id, chapter_num=chapter_num)

    return result


def _get_api_keys() -> dict:
    return {
        "anthropic_key": get_api_key("anthropic_direct"),
        "nano_key":      get_api_key("nano_gpt"),
        "openai_key":    get_api_key("openai_direct"),
        "gemini_key":    get_api_key("gemini_direct"),
        "deepseek_key":  get_api_key("deepseek_direct"),
    }


SYS_CONTRADICTION = "Ты редактор. Ищешь только прямые фактические противоречия. Только JSON."


def _check_state_contradictions(
    project_id: int, chapter_num: int, task: str,
    model_value: str, state: dict
) -> list:
    """
    Быстрая проверка: не противоречит ли задача фактам State Engine.
    Возвращает список blocking-проблем или пустой список.
    Использует дешёвую модель (resolver_model из настроек).
    """
    global_state = state.get("global_state", "").strip()
    memory       = state.get("memory_graph", "").strip()
    if not global_state and not memory:
        return []

    # Дешёвая модель из настроек
    try:
        from .db import get_conn
        with get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key='resolver_model'"
            ).fetchone()
        cheap = row["value"] if row and row["value"] else model_value
    except Exception as e:
        log.error("_check_state_contradictions get resolver_model", exc=e)
        cheap = model_value

    keys = _get_api_keys()

    prompt = f"""Проверь: есть ли в задаче главы прямые противоречия с фактами State Engine?

STATE ENGINE (персонажи, события):
{global_state[:600]}
{memory[:400]}

ЗАДАЧА ГЛАВЫ {chapter_num}:
{task}

Ищи ТОЛЬКО прямые противоречия: мёртвый персонаж появляется живым, персонаж в другом городе оказывается здесь, событие которое уже произошло случается снова, персонаж знает то что узнает только позже.

Если противоречий нет — верни: {{"contradictions": []}}
Если есть — верни: {{"contradictions": [{{"issue": "...", "detail": "...", "fix": "..."}}]}}

Только JSON."""

    import json
    import re
    raw   = call_model(cheap, SYS_CONTRADICTION, prompt, max_tokens=400, **keys)
    clean = re.sub(r"```json|```", "", raw).strip()
    try:
        data = json.loads(clean)
        return data.get("contradictions", [])
    except json.JSONDecodeError as e:
        log.error("_check_state_contradictions JSON parse", exc=e, project_id=project_id, chapter_num=chapter_num)
        return []
