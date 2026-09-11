"""
pipeline_drift.py — обнаружение дрейфа голоса.

Ответственность: проверить соответствие новой главы
голосовому эталону и сохранить результат.
"""
from typing import Callable

import re
from .db import get_active_voice, save_drift_check, should_run_drift_check
from .error_policy import handle_error, ErrorLevel

SYS_DRIFT = (
    "Ты — литературный редактор. Оцениваешь соответствие главы "
    "голосовому эталону серии. Отвечай только в указанном формате."
)

_DRIFT_PROMPT = """{label}:
{reference}

ГЛАВА {chapter_num} (первые 1200 символов):
{text}

Оцени соответствие голосу по шкале 1-10.
Сравни: темп предложений, способ описания эмоций, атрибуцию диалогов, плотность деталей.

Формат ответа — строго:
ОЦЕНКА: [число]/10
ПРОБЛЕМЫ: [список через ; или "нет"]
КРИТИЧНО: [да/нет]"""


def _get_reference(project_id: int, chapter_num: int) -> tuple[str, str] | None:
    """
    Получить эталон для сравнения.
    Возвращает (label, text) или None если эталона нет.
    """
    active_voice = get_active_voice(project_id)
    if active_voice and active_voice.get("profile"):
        return (
            f"Голосовой профиль «{active_voice['name']}»",
            active_voice["profile"][:600],
        )

    # Fallback — ранняя глава как эталон
    try:
        from .db import get_conn
        with get_conn() as conn:
            row = conn.execute(
                "SELECT number, content FROM chapters WHERE project_id=? "
                "AND number != ? ORDER BY number ASC LIMIT 1",
                (project_id, chapter_num)
            ).fetchone()
        if row and len(row["content"]) >= 300:
            return (f"Глава {row['number']} (эталон голоса)", row["content"][:1200])
    except Exception as e:
        handle_error(f"_get_reference ({project_id})", e, level=ErrorLevel.RECOVERABLE)

    return None


def _parse_drift_result(text: str) -> tuple[float, str, bool]:
    """Парсинг ответа модели. Возвращает (score, issues, critical)."""
    score_m    = re.search(r'ОЦЕНКА:\s*(\d+(?:\.\d+)?)/10', text)
    issues_m   = re.search(r'ПРОБЛЕМЫ:\s*(.+?)(?:\n|$)', text)
    critical_m = re.search(r'КРИТИЧНО:\s*(да|нет)', text, re.IGNORECASE)

    if not score_m:
        from .logger import get_logger
        get_logger(__name__).warning("_parse_drift_result: ОЦЕНКА not found, using fallback 7.0")
    score    = float(score_m.group(1)) if score_m else 7.0
    issues   = issues_m.group(1).strip() if issues_m else ""
    critical = critical_m and critical_m.group(1).lower() == "да"
    return score, issues, bool(critical)


def _build_warning(score: float, issues: str) -> str | None:
    if score < 6:
        return (f"⚠ Дрейф голоса: {score}/10. "
                f"Проблемы: {issues}. "
                f"Рекомендуется проверить голос перед следующей главой.")
    if score < 7.5:
        return f"Голос: {score}/10 — небольшие отклонения: {issues}"
    return None


def should_check_drift(project_id: int, chapter_num: int) -> bool:
    return should_run_drift_check(project_id, chapter_num)


def check_voice_drift(project_id: int, chapter_num: int,
                      chapter_text: str, model_value: str,
                      call_fn: Callable[..., str] | None = None) -> dict:
    """
    Проверить дрейф голоса новой главы.

    call_fn — функция (model, system, user, max_tokens) → str.
    Если не передана — использует внутренний _call из pipeline.
    """
    if not chapter_text or len(chapter_text) < 200:
        return {"checked": False, "reason": "text_too_short"}

    reference = _get_reference(project_id, chapter_num)
    if not reference:
        return {"checked": False, "reason": "no_reference_available"}

    label, ref_text = reference

    if call_fn is None:
        from .pipeline import _call as call_fn  # lazy import, избегаем цикла

    prompt = _DRIFT_PROMPT.format(
        label=label,
        reference=ref_text,
        chapter_num=chapter_num,
        text=chapter_text[:1200],
    )

    try:
        raw             = call_fn(model_value, SYS_DRIFT, prompt, max_tokens=300)
        score, issues, critical = _parse_drift_result(raw)
        save_drift_check(project_id, chapter_num, score, issues)
        return {
            "checked":   True,
            "score":     score,
            "issues":    issues,
            "critical":  critical,
            "warning":   _build_warning(score, issues),
            "reference": label,
        }
    except Exception as e:
        handle_error(f"check_voice_drift ({project_id}, ch{chapter_num})", e,
                     level=ErrorLevel.RECOVERABLE)
        return {"checked": False, "reason": str(e)}
