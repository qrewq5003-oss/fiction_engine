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

    except Exception as e:
        handle_error(f"continuity_checker _build_series_facts state ({project_id})", e,
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
    except Exception:
        pass
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

    # Берём первые 3000 символов главы — достаточно для проверки фактов
    chapter_sample = chapter_text[:3000]
    if len(chapter_text) > 3000:
        chapter_sample += "\n...[обрезано для проверки]"

    prompt = _CONTINUITY_PROMPT.format(
        series_facts=series_facts,
        chapter_num=chapter_num,
        chapter_text=chapter_sample,
    )

    raw = api_call_fn(prompt)

    # Парсим JSON
    import re
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not match:
        return []

    try:
        data = json.loads(match.group())
        violations = data.get("violations", [])
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
