"""
chapter_analyzer.py — Интеллектуальный анализ главы.

Проблема которую решает:
    generate_l3_summary() создаёт плоский текстовый дайджест (5 полей).
    Это storage-память: хранит что было, но не думает об этом.

    После написания главы система не знает:
    - Какие персонажные арки продвинулись / застряли
    - Какие причинно-следственные цепочки установились
    - Есть ли логические разрывы с предыдущими главами
    - Насколько насыщен конфликт
    - Какие обещания закрылись, какие открылись

Решение:
    ChapterAnalyzer — обязательный шаг после каждой главы.
    LLM заполняет структурированную запись ChapterAnalysis.
    Результат сохраняется рядом с l3_memory и доступен:
      - cognitive_memory (для весового отбора)
      - prevalidation (для проверки continuity)
      - narrative_intelligence (для отчётов)
      - unified_engine (для контекста генерации)

Использование:
    from .chapter_analyzer import ChapterAnalyzer, ChapterAnalysis

    analyzer = ChapterAnalyzer()
    analysis = analyzer.analyze(
        project_id=1,
        chapter_num=5,
        chapter_text=chapter_text,
        previous_summaries=summaries,   # из cognitive_memory
        api_call_fn=lambda p: call_model(..., p),
    )

    if analysis:
        print(analysis.logical_gaps)     # ['Марина не могла знать об этом']
        print(analysis.arc_progress)     # {'Марина': 'продвинулась: узнала о предательстве'}
        print(analysis.conflict_score)   # 0.75
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Callable

from .error_policy import error_boundary, ErrorLevel
from .logger import get_logger

log = get_logger(__name__)

LLMCaller = Callable[[str], str]


# ─── Типы данных ─────────────────────────────────────────────────────────────

@dataclass
class CharacterDelta:
    """Изменение одного персонажа в главе."""
    name: str
    knew_before: list[str] = field(default_factory=list)    # что знал до главы
    learned: list[str]     = field(default_factory=list)    # узнал в этой главе
    decided: list[str]     = field(default_factory=list)    # принял решение
    changed_state: str     = ""                              # "спокойный → в панике"
    arc_movement: str      = "neutral"                      # "forward" | "backward" | "neutral" | "resolved"


@dataclass
class CausalChain:
    """Причинно-следственная связь установленная в главе."""
    cause: str            # что произошло
    effect: str           # что это вызвало / установило
    chapter_num: int = 0  # для обратной ссылки при сохранении
    is_setup: bool = False  # True если это setup для будущего payoff


@dataclass
class ChapterAnalysis:
    """
    Структурированный анализ одной главы.
    Когнитивный слой поверх l3_memory.
    """
    project_id: int
    chapter_num: int

    # Персонажные арки
    arc_progress: dict[str, str]              = field(default_factory=dict)
    # {"Марина": "продвинулась: узнала о предательстве куратора"}

    character_deltas: list[CharacterDelta]    = field(default_factory=list)

    # Обещания
    opened_promises: list[str]                = field(default_factory=list)
    # новые setup без payoff, открытые в этой главе

    closed_promises: list[str]                = field(default_factory=list)
    # setup из прошлых глав, закрытые здесь

    # Причинно-следственные цепи
    causal_chains: list[CausalChain]          = field(default_factory=list)

    # Потенциальные разрывы
    logical_gaps: list[str]                   = field(default_factory=list)
    # ["Марина знала о коде — но ей его никто не называл до этой главы"]

    # Метрики
    conflict_score: float                     = 0.0   # 0.0–1.0
    pacing_note: str                          = ""    # "быстрый" | "медленный" | "ровный"

    # Структурные паттерны (для monotony detection — пункт 6)
    # "dialogue" | "action" | "description" | "internal" | ""
    opening_type: str                         = ""
    closing_type: str                         = ""

    # Активные сюжетные нити в конце главы
    plot_threads: dict[str, str]              = field(default_factory=dict)
    # {"поиск отца": "активна", "любовная линия": "пауза"}

    # Мета
    analysis_quality: str                     = "ok"  # "ok" | "partial" | "failed"
    raw_response: str                         = ""    # сырой ответ LLM для отладки

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def failed(cls, project_id: int, chapter_num: int) -> "ChapterAnalysis":
        """Заглушка при ошибке — лучше иметь пустой анализ, чем None."""
        return cls(
            project_id=project_id,
            chapter_num=chapter_num,
            analysis_quality="failed",
        )


# ─── Промпт ──────────────────────────────────────────────────────────────────

_ANALYSIS_SYSTEM = (
    "Ты — редактор серии. Анализируешь написанную главу структурно. "
    "Отвечаешь только валидным JSON без markdown-обёртки."
)

_ANALYSIS_PROMPT = """Проанализируй главу {chapter_num} серии.

ТЕКСТ ГЛАВЫ:
{chapter_text}

ПРЕДЫДУЩИЙ КОНТЕКСТ (саммари прошлых глав):
{previous_context}

Верни JSON строго в этом формате:
{{
  "arc_progress": {{
    "ИмяПерсонажа": "что изменилось в его арке (одно предложение)"
  }},
  "character_deltas": [
    {{
      "name": "Имя",
      "learned": ["что узнал в этой главе"],
      "decided": ["какое решение принял"],
      "changed_state": "было → стало (или пусто)",
      "arc_movement": "forward | backward | neutral | resolved"
    }}
  ],
  "opened_promises": [
    "Новый setup без payoff: что намечено но не разрешено"
  ],
  "closed_promises": [
    "Что из прошлых обещаний закрылось в этой главе"
  ],
  "causal_chains": [
    {{
      "cause": "что произошло",
      "effect": "что это установило или запустило",
      "is_setup": true/false
    }}
  ],
  "logical_gaps": [
    "Потенциальный разрыв: персонаж знает то, чего не мог знать"
  ],
  "conflict_score": 0.0,
  "pacing_note": "быстрый | медленный | ровный | нарастающий",
  "opening_type": "dialogue | action | description | internal",
  "closing_type": "dialogue | action | description | internal | cliffhanger",
  "plot_threads": {{
    "название нити": "активна | пауза | закрыта | зарождается"
  }}
}}

ПРАВИЛА:
- logical_gaps: только явные нарушения continuity, не стилистика
- conflict_score: 0.0 = нет конфликта, 1.0 = максимальное напряжение
- opened_promises: только новые в ЭТОЙ главе, не из прошлых
- closed_promises: только если payoff ЯВНО произошёл здесь
- opening_type: тип первых 2-3 предложений (dialogue/action/description/internal)
- closing_type: тип последних 2-3 предложений (те же значения + cliffhanger)
- Если данных нет — пустой массив [] или {{}}
- Только JSON. Без пояснений."""


# ─── ChapterAnalyzer ─────────────────────────────────────────────────────────

class ChapterAnalyzer:
    """
    Анализирует написанную главу и возвращает ChapterAnalysis.

    Зависимости через конструктор — тестируется без БД.
    """

    def __init__(
        self,
        get_summaries_fn=None,
        save_analysis_fn=None,
    ):
        if get_summaries_fn is None:
            from .db import get_l3_summaries
            get_summaries_fn = get_l3_summaries
        if save_analysis_fn is None:
            from .db import save_chapter_analysis
            save_analysis_fn = save_chapter_analysis

        self._get_summaries  = get_summaries_fn
        self._save_analysis  = save_analysis_fn

    def analyze(
        self,
        project_id: int,
        chapter_num: int,
        chapter_text: str,
        api_call_fn: LLMCaller,
        n_previous: int = 5,
    ) -> ChapterAnalysis:
        """
        Запустить анализ главы.

        Args:
            project_id:   ID проекта
            chapter_num:  номер анализируемой главы
            chapter_text: текст главы
            api_call_fn:  функция вызова LLM (prompt → str)
            n_previous:   сколько предыдущих саммари загружать для контекста

        Returns:
            ChapterAnalysis — всегда, даже при ошибке (analysis_quality="failed")
        """
        if not chapter_text or len(chapter_text.strip()) < 50:
            return ChapterAnalysis.failed(project_id, chapter_num)

        # Загружаем предыдущие саммари для контекста
        previous_context = self._build_previous_context(project_id, chapter_num, n_previous)

        # Ограничиваем текст — 8000 символов достаточно для анализа
        text_sample = chapter_text[:8000]
        if len(chapter_text) > 8000:
            text_sample += "\n...\n" + chapter_text[-1500:]

        prompt = _ANALYSIS_PROMPT.format(
            chapter_num=chapter_num,
            chapter_text=text_sample,
            previous_context=previous_context or "Нет предыдущих глав.",
        )

        try:
            raw = api_call_fn(prompt)
            analysis = self._parse_response(raw, project_id, chapter_num)
        except Exception as e:
            log.error("ChapterAnalyzer.analyze failed", exc=e,
                      project_id=project_id, chapter_num=chapter_num)
            return ChapterAnalysis.failed(project_id, chapter_num)

        # Сохраняем в БД (если функция доступна)
        self._persist(analysis)

        with log.context(project_id=project_id, chapter_num=chapter_num) as ctx:
            ctx.info(
                f"ChapterAnalyzer done: arcs={len(analysis.arc_progress)} "
                f"gaps={len(analysis.logical_gaps)} "
                f"conflict={analysis.conflict_score:.2f} "
                f"quality={analysis.analysis_quality}"
            )

        return analysis

    # ─── Вспомогательные ─────────────────────────────────────────────────────

    def _build_previous_context(
        self, project_id: int, chapter_num: int, n: int
    ) -> str:
        """Компактный контекст предыдущих глав для промпта анализа."""
        try:
            summaries = self._get_summaries(project_id, chapter_num, n)
            if not summaries:
                return ""
            lines = []
            for s in summaries:
                ch = s.get("chapter_num", "?")
                events = s.get("events", "")[:150]
                promises = s.get("promises", "")
                if events or promises:
                    parts = [f"Гл.{ch}: {events}"]
                    if promises:
                        parts.append(f"(обещания: {promises[:100]})")
                    lines.append(" ".join(parts))
            return "\n".join(lines)
        except Exception as e:
            log.error("_build_previous_context", exc=e, project_id=project_id)
            return ""

    def _parse_response(
        self, raw: str, project_id: int, chapter_num: int
    ) -> ChapterAnalysis:
        """Парсит JSON-ответ LLM в ChapterAnalysis."""
        try:
            clean = re.sub(r"```json|```", "", raw).strip()

            # 1. Прямой парсинг
            data = None
            try:
                data = json.loads(clean)
            except json.JSONDecodeError:
                pass

            # 2. Поиск по балансу скобок (устойчиво к тексту вокруг и кавычкам внутри)
            if data is None:
                start = clean.find('{')
                if start != -1:
                    depth, end, in_str, escape = 0, -1, False, False
                    for i, ch in enumerate(clean[start:], start):
                        if escape:
                            escape = False; continue
                        if ch == '\\' and in_str:
                            escape = True; continue
                        if ch == '"':
                            in_str = not in_str; continue
                        if not in_str:
                            if ch == '{': depth += 1
                            elif ch == '}':
                                depth -= 1
                                if depth == 0:
                                    end = i + 1; break
                    if end != -1:
                        try:
                            data = json.loads(clean[start:end])
                        except json.JSONDecodeError:
                            pass

            if data is None:
                raise ValueError("JSON не найден в ответе")

        except Exception as e:
            log.warning("ChapterAnalyzer._parse_response: JSON parse failed",
                        message=str(e))
            return ChapterAnalysis(
                project_id=project_id,
                chapter_num=chapter_num,
                analysis_quality="partial",
                raw_response=raw[:500],
            )

        # Строим character_deltas
        deltas = []
        for item in data.get("character_deltas", []):
            if not isinstance(item, dict):
                continue
            deltas.append(CharacterDelta(
                name=item.get("name", ""),
                learned=item.get("learned", []),
                decided=item.get("decided", []),
                changed_state=item.get("changed_state", ""),
                arc_movement=item.get("arc_movement", "neutral"),
            ))

        # Строим causal_chains
        chains = []
        for item in data.get("causal_chains", []):
            if not isinstance(item, dict):
                continue
            chains.append(CausalChain(
                cause=item.get("cause", ""),
                effect=item.get("effect", ""),
                chapter_num=chapter_num,
                is_setup=bool(item.get("is_setup", False)),
            ))

        # conflict_score — клипируем в [0.0, 1.0]
        try:
            score = float(data.get("conflict_score", 0.0))
            score = max(0.0, min(1.0, score))
        except (TypeError, ValueError):
            score = 0.0

        return ChapterAnalysis(
            project_id=project_id,
            chapter_num=chapter_num,
            arc_progress=data.get("arc_progress", {}),
            character_deltas=deltas,
            opened_promises=data.get("opened_promises", []),
            closed_promises=data.get("closed_promises", []),
            causal_chains=chains,
            logical_gaps=data.get("logical_gaps", []),
            conflict_score=score,
            pacing_note=data.get("pacing_note", ""),
            opening_type=data.get("opening_type", ""),
            closing_type=data.get("closing_type", ""),
            plot_threads=data.get("plot_threads", {}),
            analysis_quality="ok",
            raw_response="",   # не храним сырой ответ при успехе
        )

    @error_boundary(level=ErrorLevel.RECOVERABLE, fallback=None)
    def _persist(self, analysis: ChapterAnalysis) -> None:
        """Сохранить анализ в БД. Никогда не бросает исключение."""
        self._save_analysis(analysis.project_id, analysis.chapter_num, analysis.to_dict())


# ─── Контекстный блок для промптов ──────────────────────────────────────────

def format_analysis_for_prompt(analysis: ChapterAnalysis) -> str:
    """
    Форматирует ChapterAnalysis для вставки в промпт следующей главы.
    Компактный блок — только критически важное.
    """
    if analysis.analysis_quality == "failed":
        return ""

    lines = [f"АНАЛИЗ ГЛАВЫ {analysis.chapter_num}:"]

    # Арки — только те что двигаются
    moving_arcs = {
        name: note for name, note in analysis.arc_progress.items()
        if note and "neutral" not in note.lower()
    }
    if moving_arcs:
        lines.append("  Арки:")
        for name, note in list(moving_arcs.items())[:4]:
            lines.append(f"    {name}: {note}")

    # Логические разрывы — всегда показываем
    if analysis.logical_gaps:
        lines.append("  ⚠ Возможные разрывы:")
        for gap in analysis.logical_gaps[:3]:
            lines.append(f"    - {gap}")

    # Открытые обещания — для continuity следующей главы
    if analysis.opened_promises:
        lines.append("  Новые setup (требуют payoff):")
        for p in analysis.opened_promises[:3]:
            lines.append(f"    → {p}")

    # Конфликт и темп
    if analysis.conflict_score > 0:
        lines.append(
            f"  Конфликт: {analysis.conflict_score:.0%}"
            + (f" | Темп: {analysis.pacing_note}" if analysis.pacing_note else "")
        )

    result = "\n".join(lines)
    return result if len(result) > 30 else ""


# ─── Публичный API ────────────────────────────────────────────────────────────

# Синглтон с дефолтными зависимостями
_default_analyzer: ChapterAnalyzer | None = None


def get_analyzer() -> ChapterAnalyzer:
    """Синглтон ChapterAnalyzer с дефолтными БД-зависимостями."""
    global _default_analyzer
    if _default_analyzer is None:
        _default_analyzer = ChapterAnalyzer()
    return _default_analyzer


def analyze_chapter_deep(
    project_id: int,
    chapter_num: int,
    chapter_text: str,
    api_call_fn: LLMCaller,
) -> ChapterAnalysis:
    """
    Удобная функция для вызова без создания объекта.

    from .chapter_analyzer import analyze_chapter_deep
    analysis = analyze_chapter_deep(1, 5, text, api_fn)
    """
    return get_analyzer().analyze(project_id, chapter_num, chapter_text, api_call_fn)
