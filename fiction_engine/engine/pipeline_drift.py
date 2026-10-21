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

# Глава целиком (до лимита критика). Раньше — первые 1200 символов, около 200
# слов из 3000: модель жаловалась на сам обрез («обрыв текста на „у о“»,
# «пустая реплика „— “»), а голос судился по одному зачину (обход 20.10)
_DRIFT_PROMPT = """{label}:
{reference}

ГЛАВА {chapter_num}:
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
        from .pipeline_context import clip_profile, profile_for_chapter
        return (
            f"Голосовой профиль «{active_voice['name']}»",
            # Тот же профиль, что уходит в генерацию: сверять дрейф с урезанным
            # эталоном значит ловить отклонения от того, чего модель не видела.
            # И так же без эталонов из этой главы и следующих
            clip_profile(profile_for_chapter(project_id, chapter_num, active_voice["profile"])),
        )

    # Fallback — ранняя глава как эталон; только из прошлых (у гл.1 эталона нет)
    try:
        from .db import get_conn
        with get_conn() as conn:
            row = conn.execute(
                "SELECT number, content FROM chapters WHERE project_id=? "
                "AND number < ? ORDER BY number ASC LIMIT 1",
                (project_id, chapter_num)
            ).fetchone()
        if row and len(row["content"]) >= 300:
            # Середина главы, а не зачин: зачин нетипичен (экспозиция, крючок) —
            # дрейф мерился от него (разбор 21.10)
            body = row["content"]
            start = max(0, len(body) // 3)
            return (f"Глава {row['number']} (эталон голоса)", body[start:start + 2000])
    except Exception as e:
        handle_error(f"_get_reference ({project_id})", e, level=ErrorLevel.RECOVERABLE)

    return None


def _parse_drift_result(text: str) -> tuple[float | None, str, bool]:
    """
    Парсинг ответа модели → (score, issues, critical); оценки нет — score None.
    Раньше вместо неё подставлялось 7.0 и записывалось в журнал дрейфа как
    настоящая оценка.
    """
    # Без разметки: «**ОЦЕНКА:** 7/10» не разбиралось, и проверка не засчитывалась (разбор 21.10)
    from .pipeline_llm import _plain
    text = _plain(text)
    score_m    = re.search(r'ОЦЕНКА:\s*(\d+(?:[.,]\d+)?)\s*/\s*10', text)
    issues_m   = re.search(r'ПРОБЛЕМЫ:\s*(.+?)(?:\n|$)', text)
    critical_m = re.search(r'КРИТИЧНО:\s*(да|нет)', text, re.IGNORECASE)

    if not score_m:
        from .logger import get_logger
        get_logger(__name__).warning("_parse_drift_result: ОЦЕНКА не найдена — проверка не засчитана")
    score    = float(score_m.group(1).replace(",", ".")) if score_m else None
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


def drift_checker(model_value: str, writer: str) -> str:
    """
    Кто проверяет дрейф: model_value, если он другого семейства, чем писатель,
    иначе проверяющий другого семейства (plan_check.plan_checker_model); нет
    такого — «». Claude не судит текст Claude: в «Фоне» дрейф по тексту Sonnet
    проверял Haiku (критик), а после «Принять» — сам Sonnet (обход 20.10).
    """
    if not writer:
        return model_value
    from .pipeline_config import model_family
    if model_value and model_family(model_value) != model_family(writer):
        return model_value
    from .plan_check import plan_checker_model
    return plan_checker_model(writer)[0]


def check_voice_drift(project_id: int, chapter_num: int,
                      chapter_text: str, model_value: str,
                      call_fn: Callable[..., str] | None = None,
                      writer: str = "", save: bool = True) -> dict:
    """
    Проверить дрейф голоса новой главы.

    save — записать в журнал (расписание проверок, should_check_drift). Круг
    «Мастерской» не пишет: это черновик, журнал — по принятому тексту (после
    «Принять», auto_drift_check_if_needed). Раньше круг 1 писал оценку черновика,
    и принятый текст не проверялся вовсе: «Фон» — 7 из 8 записей до принятия.

    call_fn — функция (model, system, user, max_tokens) → str.
    Если не передана — использует внутренний _call из pipeline.
    writer — модель, писавшая главу: проверяющий берётся другого семейства.
    """
    if not chapter_text or len(chapter_text) < 200:
        return {"checked": False, "reason": "text_too_short"}

    model_value = drift_checker(model_value, writer)
    if not model_value:
        return {"checked": False, "reason": "no_checker_of_other_family"}

    reference = _get_reference(project_id, chapter_num)
    if not reference:
        return {"checked": False, "reason": "no_reference_available"}

    label, ref_text = reference

    if call_fn is None:
        from .pipeline import _call as call_fn  # lazy import, избегаем цикла

    from .pipeline_config import CRITIC_TEXT_LIMIT
    prompt = _DRIFT_PROMPT.format(
        label=label,
        reference=ref_text,
        chapter_num=chapter_num,
        text=chapter_text[:CRITIC_TEXT_LIMIT],
    )

    try:
        raw             = call_fn(model_value, SYS_DRIFT, prompt, max_tokens=300)
        score, issues, critical = _parse_drift_result(raw)
        if score is None:
            return {"checked": False, "reason": "unparsed", "raw": (raw or "")[:300]}
        if save:
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
