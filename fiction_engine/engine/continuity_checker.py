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

_SYS_CONTINUITY = (
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
  ],
  "ok": true/false
}}

Если нарушений нет — violations: [], ok: true."""


def _build_series_facts(project_id: int, chapter_num: int) -> str:
    """
    Собирает ключевые факты серии из State Engine, chapter_analysis и L3.
    Возвращает компактный текстовый блок для промпта.
    """
    parts = []

    # ── State Engine: персонажи и их состояние ────────────────────────────
    try:
        from .db import get_state
        from .db_state import parse_structured_state
        state = get_state(project_id)
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
        details = series_details(state.get("plot_matrix", ""))
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

    # ── Causal chains и opened_promises из прошлых глав ──────────────────
    try:
        from .db_chapters import get_analyses_range
        analyses = get_analyses_range(project_id, from_chapter=1, to_chapter=chapter_num - 1)

        promise_lines = []
        causal_lines  = []
        gap_lines     = []

        for a in analyses:
            ch_n = a.get("chapter_num", "?")

            for p in (a.get("opened_promises") or []):
                if p and isinstance(p, str):
                    promise_lines.append(f"  гл.{ch_n}: {p}")

            for c in (a.get("causal_chains") or []):
                if isinstance(c, dict) and c.get("is_setup") and c.get("effect"):
                    causal_lines.append(f"  гл.{ch_n}: {c.get('cause', '')} → {c['effect']}")

            for g in (a.get("logical_gaps") or []):
                if g and isinstance(g, str):
                    gap_lines.append(f"  гл.{ch_n}: {g}")

        if promise_lines:
            # Берём последние 10 — самые релевантные
            parts.append(
                "ОТКРЫТЫЕ ОБЕЩАНИЯ (setup без payoff, из прошлых глав):\n"
                + "\n".join(promise_lines[-10:])
            )
        if causal_lines:
            parts.append(
                "ПРИЧИННО-СЛЕДСТВЕННЫЕ ЦЕПИ (установленные факты):\n"
                + "\n".join(causal_lines[-8:])
            )
        if gap_lines:
            parts.append(
                "РАНЕЕ НАЙДЕННЫЕ РАЗРЫВЫ (для контекста):\n"
                + "\n".join(gap_lines[-5:])
            )

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


def _has_enough_data(project_id: int, chapter_num: int) -> bool:
    """Есть ли достаточно данных для проверки (минимум 2 прошлые главы)."""
    if chapter_num < 3:
        return False
    try:
        from .db_chapters import get_chapter_analysis
        # Проверяем что хотя бы одна прошлая глава проанализирована
        for n in range(chapter_num - 1, max(0, chapter_num - 4), -1):
            a = get_chapter_analysis(project_id, n)
            if a and a.get("analysis_quality") != "failed":
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

    Пустой список если нарушений нет или данных недостаточно.
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
    if data is None:
        return []

    try:
        violations = data.get("violations", []) if isinstance(data, dict) else []
        # Фильтруем: только реальные нарушения со severity
        return [
            v for v in violations
            if isinstance(v, dict) and v.get("violation") and v.get("fact")
        ]
    except Exception as e:
        handle_error(f"continuity_checker parse JSON ({project_id}, ch{chapter_num})", e,
                     level=ErrorLevel.RECOVERABLE)
        return []


def format_continuity_for_prompt(violations: list[dict]) -> str:
    """
    Форматирует нарушения непрерывности для вставки в critique_prompt.
    Возвращает пустую строку если нарушений нет.
    """
    if not violations:
        return ""

    critical = [v for v in violations if v.get("severity") == "critical"]
    warnings  = [v for v in violations if v.get("severity") != "critical"]

    lines = ["НАРУШЕНИЯ НЕПРЕРЫВНОСТИ СЕРИИ (проверь обязательно):"]

    for v in critical:
        lines.append(f"  ❌ КРИТИЧНО — {v['violation']}")
        lines.append(f"     Факт: {v['fact']}")

    for v in warnings:
        lines.append(f"  ⚠ ПРЕДУПРЕЖДЕНИЕ — {v['violation']}")
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
# К генерации НЕ подключено. Замер 13.10 (bench/ab-continuity-cross-2026-10-13.json,
# 36 глав из 12 серий, разметка находок судьёй Sonnet 5.5): настоящих у
# DeepSeek V4 Pro 21 из 70 (30 %), у Kimi K2.5 7 из 50; из 135 противоречий
# Sonnet поймано 17 и 5. Узкий промпт (только «проверяемые факты»): 9 находок,
# настоящая одна. Сигнал, который в двух случаях из трёх ошибается, автору
# хуже, чем никакого.

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


def format_cross_signals(found: list[dict]) -> list[str]:
    """Сигналы автору: «Противоречие с главой N: …»."""
    return [f"Противоречие с главой {x['chapter_a']}: {x['what']} («{x['quote_a']}» — "
            f"здесь «{x['quote_b']}»)." for x in found]
