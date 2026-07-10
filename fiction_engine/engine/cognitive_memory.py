"""
Cognitive Memory — интеллектуальная выборка памяти серии.

Проблема которую решает:
    К 30-й главе l3_memory содержит 30 равноценных записей.
    get_l3_context() возвращает последние 3 — и теряет критические
    события из ранних глав (нераскрытые обещания, ключевые конфликты).

Решение:
    Каждое поле саммари имеет тип с базовым весом и скоростью затухания.
    Effective score = base_weight × max(floor, 1 − decay_rate × distance)
    
    При выборке контекста:
    1. Scoring всех доступных саммари
    2. PLOT_PROMISE — всегда включаются (decay=0)
    3. Последние 2 главы — всегда включаются полностью (recency anchor)
    4. Остальные слоты — по убыванию effective_score
    5. Итоговый блок формируется с визуальным весом: важные поля выделены

Использование:
    # Вместо get_l3_context():
    from .cognitive_memory import get_cognitive_context
    ctx = get_cognitive_context(project_id, current_chapter_num)

    # Вместо get_l3_active_promises():
    from .cognitive_memory import get_weighted_promises
    promises = get_weighted_promises(project_id, current_chapter_num)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .db import get_l3_summaries
from .l3_memory import normalize_promises, get_active_promises
from .logger import get_logger

log = get_logger(__name__)


# ─── Конфигурация весов ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class MemoryField:
    """Описание поля саммари: вес и скорость затухания."""
    key: str            # ключ в словаре саммари
    label: str          # человекочитаемое название для промпта
    base_weight: float  # 1–5, важность независимо от дистанции
    decay_rate: float   # 0.0 = не затухает, 0.20 = быстро
    floor: float        # минимальный множитель при максимальной дистанции


MEMORY_FIELDS: tuple[MemoryField, ...] = (
    MemoryField("promises",   "Обещания сюжета",  base_weight=5.0, decay_rate=0.00, floor=1.00),
    MemoryField("conflicts",  "Конфликты",        base_weight=4.0, decay_rate=0.05, floor=0.20),
    MemoryField("characters", "Персонажи",        base_weight=3.0, decay_rate=0.08, floor=0.20),
    MemoryField("events",     "События",          base_weight=2.0, decay_rate=0.12, floor=0.15),
    MemoryField("mood",       "Тональность",      base_weight=1.0, decay_rate=0.20, floor=0.10),
)

# Быстрый доступ по ключу
_FIELD_MAP: dict[str, MemoryField] = {f.key: f for f in MEMORY_FIELDS}

# Порог: поле включается в контекст если его effective_score >= этого значения
INCLUSION_THRESHOLD = 0.5


# ─── Scoring ──────────────────────────────────────────────────────────────────

def _effective_score(field: MemoryField, distance: int) -> float:
    """
    Рассчитать effective score поля при заданной дистанции (в главах).
    
    effective_score = base_weight × max(floor, 1 − decay_rate × distance)
    
    distance=0  → full weight (current chapter, не используется на практике)
    distance=1  → почти полный вес
    distance=10 → значительно снижен для быстро затухающих полей
    """
    decay_factor = max(field.floor, 1.0 - field.decay_rate * distance)
    return field.base_weight * decay_factor


def score_summary(summary: dict, distance: int) -> dict[str, float]:
    """
    Рассчитать effective score для каждого поля одного саммари.

    Возвращает {field_key: score} только для непустых полей.
    Promises считаются непустыми если есть хотя бы одно активное (незакрытое).
    """
    scores: dict[str, float] = {}
    for field in MEMORY_FIELDS:
        if field.key == "promises":
            raw      = summary.get("promises", [])
            ch_num   = summary.get("chapter_num", 0)
            promises = normalize_promises(raw, ch_num)
            has_value = bool(get_active_promises(promises))
        else:
            has_value = bool(summary.get(field.key, "").strip())
        if has_value:
            scores[field.key] = _effective_score(field, distance)
    return scores


def chapter_total_score(summary: dict, distance: int) -> float:
    """Суммарный вес главы — для ранжирования при отборе."""
    return sum(score_summary(summary, distance).values())


# ─── Smart context builder ────────────────────────────────────────────────────

def get_cognitive_context(
    project_id: int,
    before_chapter: int,
    max_chapters: int = 8,
    always_recent: int = 2,
) -> str:
    """
    Умная замена get_l3_context().

    Стратегия отбора:
    1. Загружаем все доступные саммари (до max_chapters)
    2. Последние always_recent глав — включаются безусловно
    3. Promises — включаются из ВСЕХ глав (decay=0)
    4. Остальные поля — ранжируются по effective_score, берём лучшие
    """
    summaries = get_l3_summaries(project_id, before_chapter, n=max_chapters)
    if not summaries:
        return ""

    by_chapter: dict[int, dict] = {s["chapter_num"]: s for s in summaries}
    all_chapters = sorted(by_chapter.keys())
    if not all_chapters:
        return ""

    latest_chapter = max(all_chapters)
    recent_chapters = sorted(all_chapters)[-always_recent:]

    inclusions = _select_inclusions(by_chapter, all_chapters, recent_chapters, latest_chapter, max_chapters)
    result = _format_cognitive_context(by_chapter, all_chapters, recent_chapters, inclusions, latest_chapter)
    return result if len(result) > len("КОГНИТИВНАЯ ПАМЯТЬ СЕРИИ:") + 5 else ""


def _select_inclusions(
    by_chapter: dict[int, dict],
    all_chapters: list[int],
    recent_chapters: list[int],
    latest_chapter: int,
    max_chapters: int,
) -> dict[int, set[str]]:
    """
    Определяет какие поля каких глав включить в контекст.
    Возвращает {chapter_num: set(field_keys)}.
    """
    inclusions: dict[int, set[str]] = {ch: set() for ch in all_chapters}

    # Правило 1: последние always_recent глав — все непустые поля
    for ch in recent_chapters:
        s = by_chapter[ch]
        for field in MEMORY_FIELDS:
            if field.key == "promises":
                continue  # promises обрабатываются в Правиле 2
            if s.get(field.key, "").strip():
                inclusions[ch].add(field.key)

    # Правило 2: promises из всех глав (не затухают)
    for ch in all_chapters:
        _raw_p = by_chapter[ch].get("promises", "")
        _has_p = bool(_raw_p) if isinstance(_raw_p, list) else bool(str(_raw_p).strip())
        if _has_p:
            inclusions[ch].add("promises")

    # Правило 3: остальные поля по effective_score
    candidates = _collect_scored_candidates(by_chapter, all_chapters, recent_chapters, latest_chapter)
    budget = max_chapters * len(MEMORY_FIELDS) // 2
    for _score, ch, key in candidates[:budget]:
        inclusions[ch].add(key)

    return inclusions


def _collect_scored_candidates(
    by_chapter: dict[int, dict],
    all_chapters: list[int],
    recent_chapters: list[int],
    latest_chapter: int,
) -> list[tuple[float, int, str]]:
    """Собирает и сортирует кандидатов для включения по effective_score."""
    candidates: list[tuple[float, int, str]] = []
    for ch in all_chapters:
        if ch in recent_chapters:
            continue
        s = by_chapter[ch]
        distance = latest_chapter - ch
        field_scores = score_summary(s, distance)
        for key, score in field_scores.items():
            if key == "promises":
                continue
            if score >= INCLUSION_THRESHOLD:
                candidates.append((score, ch, key))
    candidates.sort(key=lambda x: -x[0])
    return candidates


def _format_cognitive_context(
    by_chapter: dict[int, dict],
    all_chapters: list[int],
    recent_chapters: list[int],
    inclusions: dict[int, set[str]],
    latest_chapter: int,
) -> str:
    """Форматирует финальный блок когнитивной памяти для промпта."""
    lines = ["КОГНИТИВНАЯ ПАМЯТЬ СЕРИИ:"]
    lines.append("(★ = высокий вес, актуальное; · = фоновое)\n")

    for ch in sorted(all_chapters):
        chapter_fields = inclusions[ch]
        if not chapter_fields:
            continue

        is_recent = ch in recent_chapters
        marker = "★" if is_recent else "·"
        lines.append(f"{marker} Глава {ch}:")

        for field in MEMORY_FIELDS:
            if field.key not in chapter_fields:
                continue

            if field.key == "promises":
                raw      = by_chapter[ch].get("promises", [])
                promises = normalize_promises(raw, ch)
                active   = get_active_promises(promises)
                if not active:
                    continue
                value = "; ".join(p["text"] for p in active)
            else:
                value = by_chapter[ch].get(field.key, "").strip()
                if not value:
                    continue

            eff_score     = _effective_score(field, latest_chapter - ch)
            weight_marker = "(!)" if eff_score >= 4.0 else "   "
            lines.append(f"  {weight_marker} {field.label}: {value}")

        lines.append("")

    return "\n".join(lines).rstrip()


# ─── Weighted promises ────────────────────────────────────────────────────────

def get_weighted_promises(
    project_id: int,
    before_chapter: int,
    n: int = 10,
) -> str:
    """
    Умная замена get_l3_active_promises().

    Возвращает только активные (незакрытые) обещания из n последних глав.
    Поддерживает оба формата: новый (список объектов) и legacy (строка).
    Сортирует: свежие обещания идут первыми.

    Returns:
        Отформатированный блок для prevalidation.
        Пустая строка если активных обещаний нет.
    """
    summaries = get_l3_summaries(project_id, before_chapter, n=n)
    if not summaries:
        return ""

    active_by_chapter: list[tuple[int, list[dict]]] = []
    for s in reversed(summaries):
        ch_num   = s["chapter_num"]
        promises = normalize_promises(s.get("promises", []), ch_num)
        active   = get_active_promises(promises)
        if active:
            active_by_chapter.append((ch_num, active))

    if not active_by_chapter:
        return ""

    lines = ["АКТИВНЫЕ СЮЖЕТНЫЕ ОБЕЩАНИЯ (не затухают, требуют закрытия):"]
    for ch_num, promises in active_by_chapter:
        for p in promises:
            lines.append(f"  [{p['id']}] Гл.{ch_num}: {p['text']}")

    return "\n".join(lines)


# ─── Диагностика ─────────────────────────────────────────────────────────────

def memory_score_report(project_id: int, before_chapter: int) -> str:
    """
    Отладочный отчёт: показывает effective scores для каждой главы и поля.
    Полезен для понимания какая память попадает в контекст.
    
    Не используется в генерации — только для диагностики.
    """
    summaries = get_l3_summaries(project_id, before_chapter, n=20)
    if not summaries:
        return "Нет L3 саммари для данного проекта."

    all_chapters = sorted(s["chapter_num"] for s in summaries)
    if not all_chapters:
        return "Пусто."

    latest = max(all_chapters)
    by_chapter = {s["chapter_num"]: s for s in summaries}

    lines = [f"Memory Score Report (before ch.{before_chapter})"]
    lines.append(f"{'Глава':>6} | " + " | ".join(f"{f.key[:8]:>8}" for f in MEMORY_FIELDS))
    lines.append("-" * 70)

    for ch in sorted(all_chapters):
        distance = latest - ch
        s = by_chapter[ch]
        scores = score_summary(s, distance)
        row = f"{ch:>6} | " + " | ".join(
            f"{scores.get(f.key, 0.0):>8.2f}" for f in MEMORY_FIELDS
        )
        lines.append(row)

    lines.append("")
    lines.append("Поля с нулём = отсутствуют в саммари (не пустые, просто не заполнены).")
    lines.append(f"Порог включения: {INCLUSION_THRESHOLD}")

    return "\n".join(lines)


# ─── Адаптер для NarrativeIntelligence ──────────────────────────────────────

def _cognitive_summaries_adapter(project_id: int, before_chapter: int, n: int = 50) -> list[dict]:
    """
    Адаптер для NarrativeIntelligence.
    Возвращает все саммари до before_chapter включительно (не взвешенные —
    NIL делает свой анализ поверх полного набора).
    
    Используется в get_nil() чтобы NIL получал данные через cognitive_memory
    слой, а не напрямую из db.
    """
    from .db import get_l3_summaries
    # NIL передаёт before_chapter+1 чтобы включить текущую —
    # нормализуем: возвращаем все до before_chapter включительно
    return get_l3_summaries(project_id, before_chapter, n=n)
