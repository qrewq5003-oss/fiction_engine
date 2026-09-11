"""
narrative_intelligence.py — Narrative Intelligence Layer (NIL).

Четыре функции:
  1. ArcTracker       — эволюция персонажных арок по главам
  2. PromiseTracker   — setup/payoff: обещания и их выполнение
  3. Contradiction    — кросс-главовые противоречия
  4. NarrativeMetrics — темп, плотность конфликта, траектория настроения

Использование:
  from .narrative_intelligence import analyze_narrative
  report = analyze_narrative(project_id=1, through_chapter=12, api_call_fn=caller)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .contracts import NarrativeReport, ArcStatus, PromiseItem, LLMCaller
from .logger import get_logger

log = get_logger(__name__)


# ─── Промпты ─────────────────────────────────────────────────────────────────

_SYS_ARC = """Ты — аналитик нарративных арок. Анализируешь эволюцию персонажей
по серии саммари. Отвечай только валидным JSON."""

_SYS_CONTRADICTION = """Ты — редактор серии. Ищешь только явные фактические
противоречия между главами. Отвечай только валидным JSON."""

_PROMISE_RESOLUTION_SYS = """Ты — нарративный аналитик. Определяешь выполнены ли
сюжетные обещания. Отвечай только валидным JSON."""


# ─── Вспомогательные ─────────────────────────────────────────────────────────

def _parse_json(raw: str) -> dict:
    """Парсит JSON из ответа LLM. Убирает markdown-обёртку."""
    clean = re.sub(r"```json|```", "", raw).strip()
    m = re.search(r"(\{.*\}|\[.*\])", clean, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    return json.loads(clean)


# ─── Вспомогательные для метрик (без LLM) ────────────────────────────────────

_CONFLICT_WORDS = [
    "конфликт", "противостояние", "угроза", "предательство",
    "опасность", "смерть", "ложь", "раскрыт", "обострился",
    "открылось", "перелом", "кризис", "атак", "схватк",
]

_MOOD_POSITIVE = {"светлое", "нежное", "радостное", "надежда", "тёплое", "спокойное"}
_MOOD_NEGATIVE = {"тревожное", "мрачное", "ужас", "отчаяние", "горе", "тёмное"}


def _conflict_word_score(conflicts: str) -> float:
    """Оценить плотность конфликта по тексту. 0.1–1.0.

    Используется как proxy для Stakes в tension_model когда нет явных данных.
    """
    count = sum(1 for w in _CONFLICT_WORDS if w in conflicts.lower())
    return round(min(1.0, 0.1 + count * 0.18), 2)


# ─── Tension Model (02_STRUCTURE_ENGINE/tension_model.md) ────────────────────
#
# Напряжение = (Stakes × 0.4) + (Urgency × 0.3) + (Uncertainty × 0.3)
#
# Целевые значения по жанру:
#   Детектив:      среднее 0.45, пики ≥ 0.75
#   Urban Fantasy: среднее 0.55, пики ≥ 0.85
#   Драма:         среднее 0.40, пики ≥ 0.70

_TENSION_TARGETS = {
    "detective":  {"avg": 0.45, "peak": 0.75},
    "thriller":   {"avg": 0.60, "peak": 0.85},
    "horror":     {"avg": 0.55, "peak": 0.85},
    "fantasy":    {"avg": 0.50, "peak": 0.80},
    "scifi":      {"avg": 0.45, "peak": 0.75},
    "romance":    {"avg": 0.35, "peak": 0.65},
    "realism":    {"avg": 0.40, "peak": 0.70},
    "default":    {"avg": 0.45, "peak": 0.75},
}


# Маппинг значений pacing_note (chapter_analyzer возвращает одно из этих)
# в urgency для tension_model.
_PACING_URGENCY: dict[str, float] = {
    # Высокий темп
    "быстрый":     0.75,
    "быстро":      0.75,
    "быстр":       0.75,
    "динамичный":  0.70,
    "экшн":        0.75,
    "action":      0.75,
    # Нарастающий — средне-высокий
    "нарастающий": 0.60,
    "нарастание":  0.60,
    "нараст":      0.60,
    # Средний
    "ровный":      0.40,
    "средний":     0.40,
    "умеренный":   0.40,
    "средн":       0.40,
    # Низкий темп
    "медленный":   0.20,
    "медленно":    0.20,
    "медленн":     0.20,
    "спокойный":   0.20,
    "лирический":  0.15,
    "рефлексия":   0.15,
}

_PACING_URGENCY_DEFAULT = 0.40  # fallback: данных нет или не распознано


def _pacing_to_urgency(pacing: str) -> tuple[float, bool]:
    """
    Перевести pacing_note в urgency для tension_model.
    Возвращает (urgency, data_available).
    data_available=False означает что pacing пустой — urgency ненадёжен.
    """
    if not pacing or not pacing.strip():
        return _PACING_URGENCY_DEFAULT, False
    p = pacing.lower().strip()
    for key, val in _PACING_URGENCY.items():
        if key in p:
            return val, True
    # Не распознано — возвращаем default, но данные технически были
    return _PACING_URGENCY_DEFAULT, True


def _tension_score(conflicts: str, pacing: str, mood: str) -> float:
    """
    Вычислить tension score по формуле tension_model.
    Stakes=конфликт, Urgency=темп, Uncertainty=полярность настроения.
    """
    stakes = _conflict_word_score(conflicts)
    urgency, _ = _pacing_to_urgency(pacing)
    polarity = _mood_polarity(mood)
    uncertainty = 0.7 if polarity == "neg" else (0.3 if polarity == "pos" else 0.5)
    return round(min(1.0, (stakes * 0.4) + (urgency * 0.3) + (uncertainty * 0.3)), 2)


def _warn_tension_pattern(
    tension_scores: list[float],
    genre_family: str = "default",
) -> list[str]:
    """
    Предупреждения на основе tension_model.
    Возвращает ВСЕ сработавшие предупреждения — не останавливается на первом.
    Ситуации не взаимоисключающие: tension может быть одновременно
    ровным И ниже нормы жанра — пользователь должен видеть оба факта.
    """
    if len(tension_scores) < 3:
        return []

    targets        = _TENSION_TARGETS.get(genre_family, _TENSION_TARGETS["default"])
    peak_threshold = targets["peak"]
    avg_target     = targets["avg"]
    recent         = tension_scores[-5:]
    actual_avg     = sum(recent) / len(recent)
    warnings: list[str] = []

    # 1. Три пика подряд — усталость читателя
    if all(t >= peak_threshold for t in tension_scores[-3:]):
        warnings.append(
            f"Три главы подряд на пике напряжения (≥{peak_threshold}). "
            "Читатель устаёт. Следующая глава должна быть разрядкой (0.3–0.5)."
        )

    # 2. Ровное напряжение — нет пиков и спадов
    if len(recent) >= 5 and round(max(recent) - min(recent), 3) < 0.2:
        warnings.append(
            f"Напряжение слишком ровное последние {len(recent)} глав "
            f"(диапазон {min(recent):.2f}–{max(recent):.2f}). "
            "Нужны пики и спады — не линейный рост."
        )

    # 3. Три главы подряд с минимальным напряжением — засуха конфликта
    if all(t < 0.25 for t in tension_scores[-3:]):
        warnings.append(
            "Три главы подряд с низким напряжением (<0.25). "
            "Нужен конфликт или откровение."
        )

    # 4. Систематическое отклонение от нормы жанра
    if abs(actual_avg - avg_target) > 0.2:
        direction = "выше" if actual_avg > avg_target else "ниже"
        warnings.append(
            f"Среднее напряжение {actual_avg:.2f} — значительно {direction} "
            f"нормы жанра ({avg_target:.2f})."
        )

    return warnings


def _mood_polarity(mood: str) -> str:
    """Вернуть 'pos', 'neg' или 'neutral'."""
    m = mood.lower()
    if any(w in m for w in _MOOD_POSITIVE):
        return "pos"
    if any(w in m for w in _MOOD_NEGATIVE):
        return "neg"
    return "neutral"


# ─── Генераторы предупреждений ────────────────────────────────────────────────

def _warn_stalled_arcs(arc_health: dict) -> str | None:
    stalled = [n for n, arc in arc_health.items() if arc.stalled]
    if stalled:
        return (f"Арки без развития (≥3 главы): {', '.join(stalled)}. "
                "Добавь событие или решение для этих персонажей.")
    return None


def _warn_overdue_promises(promise_status: list) -> str | None:
    overdue = [p for p in promise_status if p.overdue]
    if not overdue:
        return None
    texts = [f"Гл.{p.introduced_chapter}: «{p.text[:50]}»" for p in overdue[:3]]
    return "Сюжетные обещания висят >8 глав без закрытия:\n" + "\n".join(texts)



def _warn_missing_summaries(summaries: list, total_chapters: int) -> str | None:
    if total_chapters > 5 and len(summaries) < total_chapters // 2:
        return (f"L3-саммари есть только для {len(summaries)} из "
                f"{total_chapters} глав. "
                "Сгенерируй саммари для пропущенных глав для полного анализа.")
    return None


def _warn_pacing_coverage(pacing_coverage: float) -> str | None:
    """Предупреждение если tension scores неполные из-за отсутствия chapter_analysis."""
    if pacing_coverage < 0.5:
        pct = int(pacing_coverage * 100)
        return (
            f"Анализ темпа (pacing) доступен только для {pct}% глав — "
            "tension scores построены без urgency-фактора. "
            "Запусти анализ глав для повышения точности."
        )
    return None


def _generate_warnings(
    summaries: list,
    arc_health: dict,
    promise_status: list,
    contradictions: list[str],
    conflict_density: list[float],
    total_chapters: int = 0,
    genre_family: str = "default",
    pacing_coverage: float = 1.0,
) -> list[str]:
    """Собрать автоматические предупреждения без LLM."""
    # Скалярные проверки (str | None)
    scalar_checks = [
        _warn_stalled_arcs(arc_health),
        _warn_overdue_promises(promise_status),
        _warn_missing_summaries(summaries, total_chapters),
        _warn_pacing_coverage(pacing_coverage),
    ]
    warnings = [w for w in scalar_checks if w]
    # Векторная проверка (list[str]) — все сработавшие предупреждения
    warnings.extend(_warn_tension_pattern(conflict_density, genre_family=genre_family))
    # Блокирующие противоречия — всегда в предупреждениях
    warnings += [c for c in contradictions if "БЛОКИРУЮЩЕЕ" in c]
    return warnings


# ─── NarrativeIntelligence ────────────────────────────────────────────────────

class NarrativeIntelligence:
    """
    Главный анализатор нарративного состояния серии.
    Зависимости инъектируются через конструктор — тестируемо без БД.
    """

    def __init__(self, get_summaries_fn=None, get_state_fn=None, get_chapters_fn=None):
        if get_summaries_fn is None:
            from .db import get_l3_summaries
            get_summaries_fn = get_l3_summaries
        if get_state_fn is None:
            from .db import get_state
            get_state_fn = get_state
        if get_chapters_fn is None:
            from .db import get_chapters
            get_chapters_fn = get_chapters

        self._get_summaries = get_summaries_fn
        self._get_state     = get_state_fn
        self._get_chapters  = get_chapters_fn

    # ─── Основной метод ───────────────────────────────────────────────────────

    def analyze(self, project_id: int, through_chapter: int,
                api_call_fn: LLMCaller) -> NarrativeReport:
        """Полный анализ нарративного состояния (2-3 LLM-вызова)."""
        with log.context(project_id=project_id, chapter_num=through_chapter) as ctx:
            ctx.info("NIL analysis started")

        summaries = self._get_summaries(project_id, through_chapter + 1, n=50)
        summaries = [s for s in summaries if s["chapter_num"] <= through_chapter]

        if not summaries:
            return NarrativeReport(
                project_id=project_id,
                through_chapter=through_chapter,
                warnings=["Нет L3-саммари для анализа. Сгенерируйте саммари после каждой главы."],
                ok=True,
            )

        mood_trajectory  = self._extract_mood_trajectory(summaries)
        conflict_density, pacing_coverage = self._extract_conflict_density(summaries)
        promise_status   = self._track_promises(summaries, through_chapter, api_call_fn)
        arc_health       = self._analyze_arcs(summaries, api_call_fn, project_id, through_chapter)
        contradictions   = self._detect_contradictions(summaries, api_call_fn, project_id, through_chapter)

        try:
            total_chapters = len(self._get_chapters(project_id))
        except Exception:
            total_chapters = 0

        # Получаем жанр из проекта для жанровой калибровки tension_model
        try:
            from .db import get_project
            _proj = get_project(project_id)
            _genre_key = (_proj.get("genre", "") or "") if _proj else ""
            _genre_family = _genre_key.split("_")[0] if _genre_key else "default"
        except Exception:
            _genre_family = "default"

        warnings = _generate_warnings(
            summaries, arc_health, promise_status,
            contradictions, conflict_density, total_chapters,
            genre_family=_genre_family,
            pacing_coverage=pacing_coverage,
        )
        ok = not any("блокирующ" in c.lower() for c in contradictions)

        report = NarrativeReport(
            project_id=project_id,
            through_chapter=through_chapter,
            arc_health={name: arc.to_dict() for name, arc in arc_health.items()},
            promise_status=[p.to_dict() for p in promise_status],
            contradictions=contradictions,
            mood_trajectory=mood_trajectory,
            conflict_density=conflict_density,
            warnings=warnings,
            ok=ok,
        )

        with log.context(project_id=project_id, chapter_num=through_chapter) as ctx:
            ctx.info(f"NIL done: arcs={len(arc_health)} promises={len(promise_status)} "
                     f"contradictions={len(contradictions)} warnings={len(warnings)}")

        return report

    # ─── Метрики (без LLM) ────────────────────────────────────────────────────

    def get_metrics(self, project_id: int, through_chapter: int) -> dict:
        """Только числовые метрики — без LLM-вызовов."""
        summaries = self._get_summaries(project_id, through_chapter + 1, n=50)
        summaries = [s for s in summaries if s["chapter_num"] <= through_chapter]
        conflict, pacing_coverage = self._extract_conflict_density(summaries)
        return {
            "chapters_analyzed":  len(summaries),
            "mood_trajectory":    self._extract_mood_trajectory(summaries),
            "conflict_density":   conflict,
            "pacing_coverage":    round(pacing_coverage, 2),
            "promise_count":      len(self._extract_raw_promises(summaries)),
            "avg_conflict_score": round(sum(conflict) / len(conflict), 2) if conflict else 0.0,
            "mood_shift_count":   self._count_mood_shifts(summaries),
        }

    def get_promise_status(self, project_id: int, through_chapter: int) -> list[dict]:
        """Только промисы без полного анализа. Без LLM."""
        summaries = self._get_summaries(project_id, through_chapter + 1, n=50)
        summaries = [s for s in summaries if s["chapter_num"] <= through_chapter]
        return [{"chapter": ch, "promise": p}
                for ch, p in self._extract_raw_promises(summaries)]

    # ─── Arc Tracking ─────────────────────────────────────────────────────────

    def _analyze_arcs(self, summaries: list, api_call_fn: LLMCaller,
                      project_id: int, through_chapter: int) -> dict[str, ArcStatus]:
        if not summaries:
            return {}

        lines = [
            f"Гл.{s['chapter_num']}: персонажи={s.get('characters','')[:150]} "
            f"конфликты={s.get('conflicts','')[:100]}"
            for s in summaries[-15:]
            if s.get("characters") or s.get("conflicts")
        ]
        if not lines:
            return {}

        prompt = (
            "Проанализируй эволюцию персонажей по саммари глав.\n\n"
            f"САММАРИ:\n{chr(10).join(lines)}\n\n"
            'Верни JSON: {"arcs": [{"character":"Имя","status":"active|stalled|resolved|unknown",'
            '"evolution":"...","stalled":true/false,"last_chapter":N}]}\n'
            "Статусы: active — развивается, stalled — ≥3 глав без изменений, "
            "resolved — завершена, unknown — мало данных.\nТолько JSON."
        )

        try:
            data = _parse_json(api_call_fn(prompt))
            return {
                item["character"]: ArcStatus(
                    character=item["character"],
                    status=item.get("status", "unknown"),
                    last_seen_chapter=item.get("last_chapter", through_chapter),
                    evolution_notes=item.get("evolution", ""),
                    stalled=item.get("stalled", False),
                )
                for item in data.get("arcs", [])
                if item.get("character")
            }
        except Exception as e:
            log.error("NIL _analyze_arcs failed", exc=e, project_id=project_id)
            return {}

    # ─── Promise Tracking ─────────────────────────────────────────────────────

    def _track_promises(self, summaries: list, through_chapter: int,
                        api_call_fn: LLMCaller) -> list[PromiseItem]:
        raw = self._extract_raw_promises(summaries)
        if not raw:
            return []

        events_by_chapter = {
            s["chapter_num"]: s.get("events", "") + " " + s.get("conflicts", "")
            for s in summaries
        }
        resolved_map = self._check_promise_resolutions(raw, events_by_chapter, api_call_fn)

        return [
            PromiseItem(
                text=text,
                introduced_chapter=ch,
                resolved=resolved_map.get(text, {}).get("resolved", False),
                resolved_chapter=resolved_map.get(text, {}).get("chapter"),
                overdue=(not resolved_map.get(text, {}).get("resolved", False))
                        and (through_chapter - ch) > 8,
            )
            for ch, text in raw
        ]

    def _extract_raw_promises(self, summaries: list) -> list[tuple[int, str]]:
        result = []
        for s in summaries:
            text = s.get("promises", "").strip()
            if not text or text in ("нет", "—", "-", "Нет"):
                continue
            for part in re.split(r"[;;\n]", text):
                part = part.strip(" -–•")
                if len(part) > 10:
                    result.append((s["chapter_num"], part))
        return result

    def _check_promise_resolutions(self, raw_promises: list, events_by_chapter: dict,
                                    api_call_fn: LLMCaller) -> dict[str, dict]:
        if not raw_promises or not events_by_chapter:
            return {}

        promises_block = "\n".join(f"- Гл.{ch}: {text}" for ch, text in raw_promises[:10])
        events_lines   = [
            f"Гл.{ch}: {events[:150]}"
            for ch, events in sorted(events_by_chapter.items())
            if events.strip()
        ]
        events_block   = "\n".join(events_lines[-15:])

        prompt = (
            "Проверь: выполнены ли сюжетные обещания в последующих главах?\n\n"
            f"ОБЕЩАНИЯ:\n{promises_block}\n\nСОБЫТИЯ:\n{events_block}\n\n"
            'Верни JSON: {"resolutions": [{"promise":"текст","resolved":true/false,"chapter":N_или_null}]}'
            "\nТолько JSON."
        )

        try:
            data   = _parse_json(api_call_fn(prompt))
            result = {
                item["promise"]: {"resolved": item.get("resolved", False), "chapter": item.get("chapter")}
                for item in data.get("resolutions", [])
                if item.get("promise")
            }
            # Нечёткое сопоставление для ненайденных
            for _, promise_text in raw_promises:
                if promise_text not in result:
                    for key, val in result.items():
                        if promise_text[:30] in key or key[:30] in promise_text:
                            result[promise_text] = val
                            break
            return result
        except Exception as e:
            log.error("NIL _check_promise_resolutions failed", exc=e)
            return {}

    # ─── Contradiction Detection ──────────────────────────────────────────────

    def _detect_contradictions(self, summaries: list, api_call_fn: LLMCaller,
                                project_id: int, through_chapter: int) -> list[str]:
        if len(summaries) < 2:
            return []

        timeline = [
            f"Гл.{s['chapter_num']}: {s.get('events','')[:120]} "
            f"| {s.get('characters','')[:100]} | {s.get('conflicts','')[:80]}"
            for s in summaries
            if s.get("events")
        ]

        prompt = (
            "Найди явные фактические противоречия между главами серии.\n\n"
            f"ТАЙМЛАЙН:\n{chr(10).join(timeline[-20:])}\n\n"
            "Противоречия: мёртвый персонаж живёт, факт опровергается без объяснения, "
            "персонаж в двух местах, событие повторяется без памяти о первом.\n\n"
            'Верни JSON: {"contradictions": [{"chapters":[N,M],"description":"...","severity":"blocking|warning"}]}\n'
            'Если нет — {"contradictions": []}\nТолько JSON.'
        )

        try:
            data   = _parse_json(api_call_fn(prompt))
            result = []
            for item in data.get("contradictions", []):
                chapters = item.get("chapters", [])
                desc     = item.get("description", "")
                if not desc:
                    continue
                ch_str = f"Гл.{chapters[0]}↔Гл.{chapters[1]}" if len(chapters) >= 2 else ""
                prefix = "🚨 БЛОКИРУЮЩЕЕ" if item.get("severity") == "blocking" else "⚠️"
                result.append(f"{prefix} {ch_str}: {desc}")
            return result
        except Exception as e:
            log.error("NIL _detect_contradictions failed", exc=e, project_id=project_id)
            return []

    # ─── Метрики ──────────────────────────────────────────────────────────────

    def _extract_mood_trajectory(self, summaries: list) -> list[str]:
        return [f"Гл.{s['chapter_num']}: {s['mood']}" for s in summaries if s.get("mood")]

    def _extract_conflict_density(
        self, summaries: list
    ) -> tuple[list[float], float]:
        """Вычислить tension score по tension_model для каждой главы.

        Возвращает (scores, pacing_coverage).
        pacing_coverage — доля глав с реальными данными о темпе (0.0–1.0).
        pacing_note берётся из chapter_analysis (отдельная таблица).
        При отсутствии chapter_analysis urgency = default (0.40).
        """
        if not summaries:
            return [], 0.0

        project_id = summaries[0].get("project_id")
        ch_min     = summaries[0].get("chapter_num", 1)
        ch_max     = summaries[-1].get("chapter_num", 1)
        analyses_by_ch: dict[int, dict] = {}
        if project_id:
            try:
                from .db_chapters import get_analyses_range
                for a in get_analyses_range(project_id, ch_min, ch_max):
                    analyses_by_ch[a["chapter_num"]] = a
            except Exception as e:
                # Без анализов NIL отработает по одним саммари — беднее,
                # но не сломается. Отказ БД должен быть виден.
                log.error("NIL: не прочитать анализы глав", exc=e,
                          project_id=project_id)

        scores: list[float] = []
        pacing_available = 0
        for s in summaries:
            pacing = analyses_by_ch.get(s.get("chapter_num", 0), {}).get("pacing_note", "")
            _, data_ok = _pacing_to_urgency(pacing)
            if data_ok:
                pacing_available += 1
            scores.append(_tension_score(
                conflicts=s.get("conflicts", ""),
                pacing=pacing,
                mood=s.get("mood", ""),
            ))

        pacing_coverage = pacing_available / len(summaries)
        return scores, pacing_coverage

    def _count_mood_shifts(self, summaries: list) -> int:
        moods = [s["mood"] for s in summaries if s.get("mood")]
        polarities = [_mood_polarity(m) for m in moods]
        shifts = 0
        last_non_neutral: str | None = None
        for p in polarities:
            if p == "neutral":
                continue
            if last_non_neutral is not None and p != last_non_neutral:
                shifts += 1
            last_non_neutral = p
        return shifts


# ─── Синглтон и публичный API ─────────────────────────────────────────────────

_default_nil: NarrativeIntelligence | None = None


def get_nil() -> NarrativeIntelligence:
    global _default_nil
    if _default_nil is None:
        from .cognitive_memory import _cognitive_summaries_adapter
        _default_nil = NarrativeIntelligence(get_summaries_fn=_cognitive_summaries_adapter)
    return _default_nil


def analyze_narrative(project_id: int, through_chapter: int,
                      api_call_fn: LLMCaller) -> NarrativeReport:
    return get_nil().analyze(project_id, through_chapter, api_call_fn)


def get_narrative_metrics(project_id: int, through_chapter: int) -> dict:
    return get_nil().get_metrics(project_id, through_chapter)
