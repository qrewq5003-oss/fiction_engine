"""
continuity_checker.py — кросс-главный проверщик непрерывности.

Проблема: критик видит только текущую главу. Он не знает что в главе 3
персонаж поклялся никогда не делать X, а в главе 12 делает это без объяснений.

Решение: перед критикой собираем «факты серии» из:
  - State Engine   → состояние персонажей, их цели и знания
  - chapter_analysis → causal_chains и opened_promises из ВСЕХ прошлых глав
  - L3 Memory      → events и conflicts последних глав

Затем LLM-вызовом проверяем текущую главу против этих фактов.
Результат: список нарушений continuity → вставляется в critique_prompt.

Стоимость: один небольшой вызов (~400 токенов ответа) на каждую итерацию критика.
Активируется только если есть хотя бы 2 прошлые главы с данными.
"""

import json
from typing import Callable

from .error_policy import error_boundary, ErrorLevel, handle_error
from .logger import get_logger

log = get_logger(__name__)

LLMCaller = Callable[[str], str]

SYS_CONTINUITY = (
    "Ты — редактор серии, специализирующийся на непрерывности повествования. "
    "Ищешь только конкретные, явные нарушения фактов серии в новой главе. "
    "Не стилистику, не предположения — только то что явно противоречит "
    "установленным фактам. Отвечаешь только валидным JSON без пояснений."
)

_CONTINUITY_PROMPT = """Проверь новую главу на нарушения непрерывности серии.

УСТАНОВЛЕННЫЕ ФАКТЫ СЕРИИ:
{series_facts}

НОВАЯ ГЛАВА {chapter_num}:
{chapter_text}

Найди нарушения — только явные противоречия установленным фактам.
НЕ включай: стилистические замечания, предположения, «возможно», «кажется».

Верни JSON:
{{
  "violations": [
    {{
      "fact": "Установленный факт (откуда): ...",
      "violation": "Что в новой главе противоречит этому факту",
      "severity": "critical | warning"
    }}
  ]
}}

Если нарушений нет — violations: []."""


def _build_series_facts(project_id: int, chapter_num: int) -> str:
    """
    Собирает ключевые факты серии из State Engine, chapter_analysis и L3.
    Возвращает компактный текстовый блок для промпта.
    """
    parts = []

    # ── State Engine: персонажи и их состояние ────────────────────────────
    try:
        from .db_state import parse_structured_state, state_for_chapter
        state = state_for_chapter(project_id, chapter_num)
        structured = parse_structured_state(state)

        char_lines = []
        for name, ch in structured.get("characters", {}).items():
            bits = []
            if ch.get("goal"):     bits.append(f"цель: {ch['goal']}")
            if ch.get("deep_goal"): bits.append(f"глубинная цель: {ch['deep_goal']}")
            if ch.get("knows"):    bits.append(f"знает: {ch['knows']}")
            if ch.get("ignores"):  bits.append(f"НЕ знает: {ch['ignores']}")
            if ch.get("state"):    bits.append(f"состояние: {ch['state']}")
            if bits:
                char_lines.append(f"  {name}: " + "; ".join(bits))

        if char_lines:
            parts.append("ПЕРСОНАЖИ (State Engine):\n" + "\n".join(char_lines))

        world = structured.get("world", {})
        forbidden = world.get("forbidden", "")
        if forbidden:
            parts.append(f"НЕЛЬЗЯ ДОПУСТИТЬ (из State Engine): {forbidden}")

        from .db_state import series_details
        details = series_details(state.get("plot_matrix", ""), chapter_num)
        if details:
            parts.append("ДЕТАЛИ СЕРИИ (вещи, места, время, числа):\n"
                         + "\n".join(f"  {d}" for d in details[-30:]))

    except Exception as e:
        handle_error(f"continuity_checker _build_series_facts state ({project_id})", e,
                     level=ErrorLevel.RECOVERABLE)

    try:
        from .text_signals import previous_chapters, series_names
        names = series_names(previous_chapters(project_id, chapter_num, n=1000))
        if names:
            parts.append("ИМЕНА С ОТЧЕСТВАМИ (как впервые названы): " + ", ".join(names[:40]))
    except Exception as e:
        handle_error(f"continuity_checker _build_series_facts names ({project_id})", e,
                     level=ErrorLevel.RECOVERABLE)

    try:
        from .series_bible import bible_block
        b = bible_block(project_id, before_chapter=chapter_num)
        if b:
            parts.append(b)
    except Exception as e:
        handle_error(f"continuity_checker _build_series_facts bible ({project_id})", e,
                     level=ErrorLevel.RECOVERABLE)

    # ── Causal chains и opened_promises из прошлых глав ──────────────────
    try:
        from .db_chapters import get_analyses_range
        analyses = get_analyses_range(project_id, from_chapter=1, to_chapter=chapter_num - 1)

        promise_lines = []
        causal_lines  = []

        # Открытые обещания — из L3, где отмечено их закрытие. opened_promises
        # анализа глав закрытий не знают: закрытые уходили проверке как открытые
        # (разбор 21.10)
        from .db_narrative import get_l3_summaries
        from .l3_memory import get_active_promises, normalize_promises
        for s in get_l3_summaries(project_id, chapter_num, n=10000):
            for p in get_active_promises(normalize_promises(s.get("promises") or [], s["chapter_num"]), chapter_num):
                if p.get("text"):
                    promise_lines.append(f"  гл.{s['chapter_num']}: {p['text']}")

        for a in analyses:
            ch_n = a.get("chapter_num", "?")

            for c in (a.get("causal_chains") or []):
                if isinstance(c, dict) and c.get("is_setup") and c.get("effect"):
                    causal_lines.append(f"  гл.{ch_n}: {c.get('cause', '')} → {c['effect']}")

        if promise_lines:
            # Последние 15 — самые свежие
            parts.append(
                # Не факт, которому можно противоречить: глава, их не закрывшая, — не нарушение
                "ОТКРЫТЫЕ ОБЕЩАНИЯ ПРОШЛЫХ ГЛАВ (не нарушение, если эта глава их не закрывает):\n"
                + "\n".join(promise_lines[-15:])
            )
        if causal_lines:
            parts.append(
                "ПРИЧИННО-СЛЕДСТВЕННЫЕ ЦЕПИ (установленные факты):\n"
                + "\n".join(causal_lines[-8:])
            )
        # Разрывы прошлых глав — не факты серии, а их ошибки: проверяющий
        # приписывал их новой главе (как критик, step_critique, 21.10)

    except Exception as e:
        handle_error(f"continuity_checker _build_series_facts analyses ({project_id})", e,
                     level=ErrorLevel.RECOVERABLE)

    # ── L3 Memory: события и конфликты ────────────────────────────────────
    try:
        from .db_narrative import get_l3_summaries
        summaries = get_l3_summaries(project_id, before_chapter=chapter_num, n=3)
        if summaries:
            l3_lines = []
            for s in summaries:
                bits = []
                if s.get("events"):    bits.append(f"события: {s['events']}")
                if s.get("conflicts"): bits.append(f"конфликты: {s['conflicts']}")
                if bits:
                    l3_lines.append(f"  гл.{s['chapter_num']}: " + "; ".join(bits))
            if l3_lines:
                parts.append("L3 КОНТЕКСТ (последние главы):\n" + "\n".join(l3_lines))
    except Exception as e:
        handle_error(f"continuity_checker _build_series_facts l3 ({project_id})", e,
                     level=ErrorLevel.RECOVERABLE)

    if not parts:
        return ""
    return "\n\n".join(parts)


def skip_reason(project_id: int, chapter_num: int) -> str:
    """Почему check_continuity проверять не станет; «» — проверит.

    Пустой список нарушений означал и «проверено, чисто», и «не с чем
    сравнивать»: страница главы 1 отвечала «✓ Нарушений не найдено», не
    вызвав модель.
    """
    if _has_enough_data(project_id, chapter_num):
        return ""
    if chapter_num < 3:
        return "Проверять не с чем: нужны минимум две прошлые главы"
    # Анализ главы пишется «Принять» и «Пересчитать по тексту» (разбор 21.10:
    # подсказка вела на ручной «Анализ», который поверх главы двоил детали)
    return ("Проверять не с чем: прошлые главы не проанализированы — «Пересчитать по тексту» "
            "на странице каждой из них")


def _has_enough_data(project_id: int, chapter_num: int) -> bool:
    """Есть ли достаточно данных для проверки (минимум 2 прошлые главы)."""
    if chapter_num < 3:
        return False
    try:
        from .db_chapters import get_chapter_analysis
        # Проверяем что хотя бы одна прошлая глава проанализирована
        for n in range(chapter_num - 1, max(0, chapter_num - 4), -1):
            a = get_chapter_analysis(project_id, n)
            if a and a.get("analysis_quality", "ok") == "ok":
                return True
    except Exception as e:
        handle_error("_has_enough_data: не прочитать анализ глав", e,
                     level=ErrorLevel.RECOVERABLE)
    return False


@error_boundary(level=ErrorLevel.RECOVERABLE, fallback=[])
def check_continuity(
    project_id: int,
    chapter_num: int,
    chapter_text: str,
    api_call_fn: LLMCaller,
) -> list[dict]:
    """
    Проверить главу на нарушения непрерывности серии.

    Возвращает список нарушений:
    [{"fact": str, "violation": str, "severity": "critical"|"warning"}, ...]

    Пустой список если нарушений нет, данных недостаточно — или проверка
    сорвалась. Где сбой надо показать — check_continuity_or_raise.
    """
    return check_continuity_or_raise(project_id, chapter_num, chapter_text, api_call_fn)


def check_continuity_or_raise(
    project_id: int,
    chapter_num: int,
    chapter_text: str,
    api_call_fn: LLMCaller,
) -> list[dict]:
    """
    То же, но сбой (модель не ответила, ответ не разобран) — исключение, а не
    пустой список: «Проверить непрерывность» показывала «✓ Нарушений не найдено»
    и на сбое (разбор 21.10).
    """
    if not _has_enough_data(project_id, chapter_num):
        return []

    series_facts = _build_series_facts(project_id, chapter_num)
    if not series_facts:
        return []

    # Глава уходит целиком. Раньше здесь стояли первые 3000 символов с
    # комментарием «достаточно для проверки фактов» — утверждение, которое
    # никто не проверял. Для главы в 11 000 символов это 26 %.
    #
    # Проверено подсадкой 14.09: одно и то же противоречие («Лукаш
    # расписался ПРАВОЙ рукой и протянул ПАВЛУ, который погиб в главе 2,
    # нефритовый секстант») ставилось на 5 % и на 85 % главы. Метка
    # уникальна, чтобы совпадение нельзя было спутать с упоминанием Павла
    # в самом тексте.
    #
    #     подсадка на 85 %:  обрезка 3000 — не найдено (её там и нет)
    #                        полный текст — найдено, метка названа дословно
    #
    # Факты — имена, предметы, обещания — рассыпаны по всей главе, а не
    # собраны в начале. Выборка здесь режет не лишнее, а искомое.
    #
    # Потолок оставлен от вырожденного ответа, тот же, что у критика.
    from .pipeline_config import CRITIC_TEXT_LIMIT
    chapter_sample = chapter_text[:CRITIC_TEXT_LIMIT]
    if len(chapter_text) > CRITIC_TEXT_LIMIT:
        chapter_sample += "\n...[обрезано для проверки]"

    prompt = _CONTINUITY_PROMPT.format(
        series_facts=series_facts,
        chapter_num=chapter_num,
        chapter_text=chapter_sample,
    )

    raw = api_call_fn(prompt)

    # Парсим JSON общим терпимым разбором: своя выемка `{.*}` ломалась
    # на обрамлении ```json и на ответе, обрезанном лимитом токенов.
    from .pipeline_llm import parse_json
    data = parse_json(raw)
    if not isinstance(data, dict):
        raise ValueError("ответ проверки непрерывности не разобран")
    violations = data.get("violations") or []
    # Только настоящие нарушения: с фактом и описанием
    return [v for v in violations if isinstance(v, dict) and v.get("violation") and v.get("fact")]


def format_continuity_for_prompt(violations: list[dict]) -> str:
    """
    Форматирует нарушения непрерывности для вставки в critique_prompt.
    Возвращает пустую строку если нарушений нет.
    """
    if not violations:
        return ""

    critical = [v for v in violations if v.get("severity") == "critical"]
    warnings  = [v for v in violations if v.get("severity") != "critical"]

    # Проверка по выжимке State, без цитат из главы: не «проверь обязательно / ❌ КРИТИЧНО»,
    # а сверка (разбор формулировок 26.10); «ГРУБО» по связности — только с цитатой
    lines = ["ВОЗМОЖНЫЕ РАСХОЖДЕНИЯ С ФАКТАМИ СЕРИИ (проверка по выжимке, без цитат — сверь с текстом главы):"]

    for v in critical:
        lines.append(f"  ⚠ вероятно — {v['violation']}")
        lines.append(f"     Факт: {v['fact']}")

    for v in warnings:
        lines.append(f"  ? возможно — {v['violation']}")
        lines.append(f"     Факт: {v['fact']}")

    return "\n".join(lines)


# ─── Сверка с текстом прошлых глав ───────────────────────────────────────────
#
# check_continuity сверяет главу с выжимкой: State, анализ глав, L3. Этажа
# квартиры, цвета шарфа и того, что плащ уже изъят, в выжимке нет — и судья
# Sonnet находит их в каждой серии (замер 12.10, bench/ab-series-names-2026-10-12.json:
# 13 противоречий на серию из 4 глав, отчества уже не в счёт). Здесь модель
# видит полный текст последних глав и новую главу и выписывает противоречие
# парой цитат. Цитаты проверяются по тексту: что не найдено — отброшено, так
# что выдумать противоречие модель не может.
#
# К генерации подключено только по выбору автора — см. cross_check_signals ниже. Замер 13.10 (bench/ab-continuity-cross-2026-10-13.json,
# 36 глав из 12 серий, разметка находок судьёй Sonnet 5.5): настоящих у
# DeepSeek V4 Pro 21 из 70 (30 %), у Kimi K2.5 7 из 50; из 135 противоречий
# Sonnet поймано 17 и 5. Узкий промпт (только «проверяемые факты»): 9 находок,
# настоящая одна. Сигнал, который в двух случаях из трёх ошибается, автору
# хуже, чем никакого.
#
# Проверяющий другого семейства, чем писатель (14.10,
# bench/ab-continuity-sonnet-2026-10-14.json): Sonnet 5.5 на 24 главах
# DeepSeek — 108 находок, настоящих по Kimi 77 %, по Opus 84 %, по обоим 70 %;
# из 63 противоречий, которые Sonnet находит, читая серию целиком, поймано 43.
# GLM 5.2 там же — 42 % и 3 из 66. Годится только сильный проверяющий.

CROSS_LOOKBACK = 3            # сколько прошлых глав показывать целиком
CROSS_PREV_CHARS = 60000      # потолок на прошлые главы, старшие отрезаются первыми
CROSS_MAX = 8                 # больше автору за раз не показываем

_CROSS_PROMPT = """Ниже прошлые главы серии и новая глава {num}. Найди, где НОВАЯ глава
противоречит прошлым: факт, заданный раньше, нарушен — имя, внешность, рана,
одежда, вещь и где она, место, этаж, время, день, погода, кто что знает,
видел или говорил, что уже произошло. Не считай противоречием развитие (герой
узнал новое, передумал), ложь персонажа, если текст её так и подаёт, и стиль.
Цитаты точные, 5–15 слов: quote_a — из прошлой главы, quote_b — из новой.

{prev}

=== НОВАЯ ГЛАВА {num} ===
{text}

Ответь JSON без пояснений вокруг (нет противоречий — пустой список):
{{"contradictions": [{{"chapter_a": 3, "quote_a": "…", "quote_b": "…", "what": "…"}}]}}"""


def _norm_quote(s: str) -> str:
    import re
    s = (s or "").lower().replace("ё", "е")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip()


def quote_in(quote: str, text: str) -> bool:
    """Цитата есть в тексте; части через «…» — по отдельности, каждая от 3 слов."""
    import re
    t = _norm_quote(text)
    parts = [_norm_quote(p) for p in re.split(r"\.\.\.|…", quote or "")]
    parts = [p for p in parts if len(p.split()) >= 3]
    return bool(parts) and all(p in t for p in parts)


def plan_block(plan: str) -> str:
    """План главы для правщика: что он велит раскрыть или изменить — не ошибка, не исправлять."""
    plan = (plan or "").strip()
    if not plan:
        return ""
    return ("\nПЛАН ЭТОЙ ГЛАВЫ (от автора): что в нём раскрывается, меняется или "
            "признаётся — задумано, это не противоречие:\n" + plan[:3000] + "\n")


def check_against_chapters(chapter_num: int, chapter_text: str, previous: list[dict],
                           api_call_fn: LLMCaller) -> list[dict]:
    """
    Противоречия новой главы с текстом прошлых. previous — [{number, content}]
    по возрастанию. Возвращает только пары, обе цитаты которых нашлись:
    [{chapter_a, quote_a, quote_b, what}].
    """
    prev = [p for p in previous if (p.get("content") or "").strip()][-CROSS_LOOKBACK:]
    if not prev or not (chapter_text or "").strip():
        return []
    while len(prev) > 1 and sum(len(p["content"]) for p in prev) > CROSS_PREV_CHARS:
        prev = prev[1:]
    from .pipeline_config import CRITIC_TEXT_LIMIT
    blocks = "\n\n".join(f"=== ГЛАВА {p['number']} ===\n{p['content'][-CROSS_PREV_CHARS:]}"
                         for p in prev)
    raw = api_call_fn(_CROSS_PROMPT.format(num=chapter_num, prev=blocks,
                                           text=chapter_text[:CRITIC_TEXT_LIMIT]))
    from .pipeline_llm import parse_json
    data = parse_json(raw)
    items = data if isinstance(data, list) else \
        data.get("contradictions") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("проверка непрерывности: ответ модели не разобран")
    by_num = {p["number"]: p["content"] for p in prev}
    out = []
    for x in items:
        if not isinstance(x, dict):
            continue
        try:
            a = int(x.get("chapter_a"))
        except (TypeError, ValueError):
            continue
        if a in by_num and quote_in(x.get("quote_a"), by_num[a]) \
                and quote_in(x.get("quote_b"), chapter_text):
            out.append({"chapter_a": a, "quote_a": str(x["quote_a"]).strip(),
                        "quote_b": str(x["quote_b"]).strip(), "what": str(x.get("what") or "").strip()})
    return out[:CROSS_MAX]


_SELF_PROMPT = """Ниже глава {num}. Найди, где она противоречит САМОЙ СЕБЕ: факт, заданный в
одном месте главы, нарушен в другом — имя, этаж, время, день, одежда, вещь и
где она, кто где был, кто что знает или говорил, жив или мёртв. Не считай
противоречием развитие (герой узнал новое, передумал), ложь персонажа, если
текст её так и подаёт, и стиль. Цитаты точные, 5–15 слов, обе из этой главы:
quote_a — раньше по тексту, quote_b — позже.

=== ГЛАВА {num} ===
{text}

Ответь JSON без пояснений вокруг (нет противоречий — пустой список):
{{"contradictions": [{{"quote_a": "…", "quote_b": "…", "what": "…"}}]}}"""


def check_self_contradictions(chapter_num: int, chapter_text: str,
                              api_call_fn: LLMCaller) -> list[dict]:
    """
    Противоречия главы с самой собой — после точечной правки, когда факт
    исправлен не во всех местах. Формат как у check_against_chapters,
    chapter_a = номер этой же главы; обе цитаты проверяются по тексту.
    """
    if not (chapter_text or "").strip():
        return []
    from .pipeline_config import CRITIC_TEXT_LIMIT
    raw = api_call_fn(_SELF_PROMPT.format(num=chapter_num, text=chapter_text[:CRITIC_TEXT_LIMIT]))
    from .pipeline_llm import parse_json
    data = parse_json(raw)
    items = data if isinstance(data, list) else \
        data.get("contradictions") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("проверка главы на себя: ответ модели не разобран")
    out = []
    for x in items:
        if isinstance(x, dict) and quote_in(x.get("quote_a"), chapter_text) \
                and quote_in(x.get("quote_b"), chapter_text):
            out.append({"chapter_a": chapter_num, "quote_a": str(x["quote_a"]).strip(),
                        "quote_b": str(x["quote_b"]).strip(), "what": str(x.get("what") or "").strip()})
    return out[:CROSS_MAX]


def format_cross_signals(found: list[dict]) -> list[str]:
    """Сигналы автору: «Противоречие с главой N: …»."""
    return [f"Противоречие с главой {x['chapter_a']}: {x['what']} («{x['quote_a']}» — "
            f"здесь «{x['quote_b']}»)." for x in found]


# ─── Проверка после генерации: подключение к движку ──────────────────────────
#
# Выключена, пока автор не выбрал модель («Настройки → Проверка
# непрерывности», ключ continuity_model). Слабый проверяющий даёт сигнал,
# который чаще ошибается, чем нет (DeepSeek 30 %, GLM 42 %, GPT-6 Luna — по
# обоим судьям 2 из 33), поэтому без выбора автора вызова нет.
#
# Замер 15.10 (bench/ab-continuity-gpt-2026-10-15.json): GPT-6.1 Sol через
# подписку ChatGPT — по обоим судьям 84 % настоящих, полнота 42 из 68; Sonnet
# 5.5 — 70 % и 43 из 63. Проверяющий того же семейства, что писатель, не
# замерен; модель склонна не видеть собственных ошибок, поэтому — предупреждение.

CONTINUITY_MODEL_KEY = "continuity_model"
_SYS_CROSS = "Ты строгий литературный редактор серии. Отвечаешь только JSON."


def continuity_model() -> str:
    """Модель проверки непрерывности из настроек; «» — проверка выключена."""
    from .db_settings import get_setting
    return (get_setting(CONTINUITY_MODEL_KEY) or "").strip()


def continuity_checker_for(model_gen: str) -> str:
    """
    Проверяющий непрерывности для текста писателя model_gen: из настроек, если
    другой семьи; иначе проверяющий другой семьи (plan_check.plan_checker_model);
    нет такого — «» (проверки нет). Проверка выключена в настройках — «».

    Раньше проверяющий брался из настроек как есть и при той же семье только
    предупреждал. Набор ролей ставит его другой семьи, но «Ещё круг» в старом
    запуске после смены набора давал Sonnet по тексту Sonnet (разбор 21.10).
    """
    model = continuity_model()
    if not (model and model_gen):
        return model
    from .pipeline_config import model_family
    if model_family(model) != model_family(model_gen):
        return model
    from .plan_check import plan_checker_model
    return plan_checker_model(model_gen)[0]


def same_family_note(model_gen: str, model_check: str) -> str:
    """Предупреждение, если проверяющий из того же семейства, что писатель; иначе «»."""
    from .pipeline_config import model_family
    if not model_gen or not model_check or model_family(model_gen) != model_family(model_check):
        return ""
    return (f"Проверка непрерывности: проверяющий ({model_check.split('::')[-1]}) из того же "
            f"семейства, что писатель — свои ошибки модель видит хуже. Надёжнее проверяющий "
            f"другого семейства («Настройки → Проверка непрерывности»).")


def cross_check_signals(project_id: int, chapter_num: int, text: str, model_gen: str,
                        call_fn: Callable[..., str]) -> list[str]:
    """
    Сигналы автору по сверке новой главы с текстом прошлых: до CROSS_MAX
    противоречий парами цитат. call_fn(model, system, user, max_tokens=…) -> str.
    Модель не выбрана, прошлых глав нет или вызов упал — пустой список.
    """
    return cross_check_and_fix(project_id, chapter_num, text, model_gen, call_fn, fix=False)[1]


# ─── Правка по находкам ──────────────────────────────────────────────────────
#
# Замер 15.10 (bench/ab-continuity-fix-2026-10-15.json, 24 главы DeepSeek,
# находки Sol): правщик Sonnet 5.5 — находок 104 → 10, проза после правки
# устойчиво лучше по судье GPT 11 : 5 (судья видит, что связность выросла,
# а проза та же); изменено 1.3 % слов. DeepSeek как правщик снимает почти
# столько же (104 → 11), но доводит факт не по всей главе — глава начинает
# противоречить сама себе, и судья устойчиво за исходник 12 : 5. Поэтому
# правщик — отдельная настройка, а не писатель главы. Не задан — правки нет,
# автору идут сигналы, как раньше.

CONTINUITY_FIX_MODEL_KEY = "continuity_fix_model"

# Второй круг (тот же замер, bench/ab-continuity-fix-r2): перепроверка после
# правки находит ещё противоречия — за проход проверяющий видит не всё. Правка
# по ним снимает 47 из 49, проза по судье не хуже (8 : 7), изменено 0.9 %
# слов. Круг идёт, только если после прошлого что-то осталось; третий круг
# не мерили.
CROSS_FIX_ROUNDS = 2


def continuity_fix_model() -> str:
    """Модель правки по находкам проверки; «» — правки нет, только сигналы."""
    from .db_settings import get_setting
    return (get_setting(CONTINUITY_FIX_MODEL_KEY) or "").strip()


def _budget(model: str, default: int) -> int:
    # Подписка Claude тратит бюджет и на скрытое размышление, как у судей
    return 32000 if model.startswith("claude_subscription::") else default


def cross_check_and_fix(project_id: int, chapter_num: int, text: str, model_gen: str,
                        call_fn: Callable[..., str], fix: bool = True,
                        report: dict | None = None) -> tuple[str, list[str]]:
    """
    Сверка новой главы с прошлыми и, если выбран правщик, точечная правка по
    находкам с перепроверкой. Возвращает (текст, сигналы автору): после правки
    в сигналах — сколько исправлено и то, что осталось. Проверяющий не выбран,
    прошлых глав нет или проверка упала — текст как есть, сигналов нет; упала
    правка — текст как есть, сигналы по находкам.

    report — для карточки главы: checker, fixer, rounds, found (первые
    находки), edits ([{what, old, new}] — замены по кругам), left (что
    осталось), recheck_failed. Заполняется, только если проверка прошла.
    """
    model = continuity_checker_for(model_gen)
    if not model or not project_id or not (text or "").strip():
        return text, []
    from .text_signals import previous_chapters
    prev = previous_chapters(project_id, chapter_num, CROSS_LOOKBACK)
    if not prev:
        return text, []
    # План главы — правщику: в книге-прогоне 17.10 признание убийцы по плану
    # главы 12 было принято за противоречие с её ложью в главе 10, и правщик
    # переписал признание в отрицание. Проверяющему план и правило о
    # разоблачениях не даются: замер на Sol (24 главы, 98 размеченных
    # противоречий) — с ними найдено 56 из 98 против 91–98, слишком много
    # настоящих противоречий в репликах пропадало. Разоблачение остаётся
    # сигналом автору, но текст правщик не трогает
    try:
        from .db_narrative import get_director_note
        plan = get_director_note(project_id, chapter_num) or ""
    except Exception as e:
        handle_error("cross_check_and_fix: план главы", e, level=ErrorLevel.RECOVERABLE)
        plan = ""

    def against_previous(t: str) -> list[dict]:
        return check_against_chapters(chapter_num, t, prev, lambda p: call_fn(
            model, _SYS_CROSS, p, max_tokens=_budget(model, 4000)))

    where = f"({project_id}, ch{chapter_num})"
    try:
        found = against_previous(text)
    except Exception as e:
        handle_error(f"cross_check_signals {where}", e, level=ErrorLevel.RECOVERABLE)
        return text, []
    note = same_family_note(model_gen, model)
    head = [note] if note and found else []
    fixer = continuity_fix_model() if fix else ""
    rep: dict = report if report is not None else {}
    rep.update(checker=model, fixer=fixer, rounds=0, found=found, edits=[], left=found,
               recheck_failed=False, note=note if found else "")
    if not found or not fixer:
        return text, head + format_cross_signals(found)

    from .continuity_fix import SYS_FIX, fix_contradictions
    total = edits = rounds = 0
    left = found
    while left and rounds < CROSS_FIX_ROUNDS:
        try:
            res = fix_contradictions(chapter_num, text, left, prev, lambda p: call_fn(
                fixer, SYS_FIX, p, max_tokens=_budget(fixer, 8000)), plan=plan)
        except Exception as e:
            handle_error(f"continuity_fix {where}", e, level=ErrorLevel.RECOVERABLE)
            break
        if not res["applied"]:
            break
        text, rounds = res["text"], rounds + 1
        total, edits = total + len(left), edits + len(res["applied"])
        whats = "; ".join(f["what"] for f in left)
        rep["edits"] += [{"round": rounds, "what": whats, "old": e["old"], "new": e["new"]}
                         for e in res["applied"]]
        rep["rounds"] = rounds
        try:
            left = against_previous(text)
        except Exception as e:
            handle_error(f"cross_check_signals (перепроверка) {where}", e, level=ErrorLevel.RECOVERABLE)
            rep["recheck_failed"] = True
            done = _fix_summary(fixer, total, edits, rounds)
            return text, head + [done + "; перепроверка не удалась — проверь эти места:"] + \
                format_cross_signals(left)
    if not rounds:
        return text, head + format_cross_signals(found)
    rep["left"] = left
    done = _fix_summary(fixer, total, edits, rounds)
    return text, head + [done + (f"; осталось {len(left)}:" if left else "; не осталось.")] + \
        format_cross_signals(left)


def _fix_summary(fixer: str, total: int, edits: int, rounds: int) -> str:
    return (f"Правка непрерывности ({fixer.split('::')[-1]}): противоречий с прошлыми главами "
            f"{total}, замен {edits}" + (f", кругов {rounds}" if rounds > 1 else ""))
