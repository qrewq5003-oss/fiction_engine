"""
contracts.py — Формальные интерфейсы (Protocol) всех компонентов системы.

Зачем Protocol, а не ABC:
  Protocol — структурная типизация. Существующий код не нужно менять
  (добавлять наследование). Если модуль реализует нужные методы —
  он уже удовлетворяет контракту. Это важно для системы где уже есть
  работающий код.

  ABC — номинальная типизация. Требует явного наследования.
  Оправдан когда контракт вводится с нуля.

Как использовать:
  from .contracts import LLMCaller, SummaryStore
  def my_func(caller: LLMCaller, store: SummaryStore): ...

  # Проверка соответствия в тестах:
  from typing import get_type_hints
  assert isinstance(my_obj, LLMCaller)  # работает без наследования
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


# ─── LLM ─────────────────────────────────────────────────────────────────────

@runtime_checkable
class LLMCaller(Protocol):
    """
    Что-либо умеющее вызвать языковую модель.

    Реализуется: pipeline._call(), pipeline._make_model_caller().*
    Используется: l3_memory, prevalidation, narrative_intelligence.
    """
    def __call__(self, prompt: str) -> str:
        """Принять промпт, вернуть ответ модели."""
        ...


@runtime_checkable
class FullModelCaller(Protocol):
    """
    Расширенный вызов с системным промптом и лимитом токенов.

    Реализуется: api.call_model().
    """
    def __call__(
        self,
        model_value: str,
        system: str,
        user: str,
        max_tokens: int,
        **kwargs: str,
    ) -> str:
        ...


# ─── Хранилище саммари ────────────────────────────────────────────────────────

@runtime_checkable
class SummaryStore(Protocol):
    """
    Хранилище L3-саммари глав.

    Реализуется: db_projects (функции save_l3_summary, get_l3_summaries и т.д.)
    Используется: l3_memory, narrative_intelligence, prevalidation.
    """
    def save_l3_summary(self, project_id: int, chapter_num: int, summary: dict) -> bool:
        ...

    def get_l3_summaries(self, project_id: int, before_chapter: int, n: int) -> list[dict]:
        ...

    def get_l3_summary(self, project_id: int, chapter_num: int) -> dict | None:
        ...


# ─── Хранилище глав ───────────────────────────────────────────────────────────

@runtime_checkable
class ChapterStore(Protocol):
    """
    Хранилище глав проекта.

    Реализуется: db_projects.
    Используется: pipeline, state, narrative_intelligence.
    """
    def save_chapter(self, project_id: int, number: int,
                     content: str, title: str) -> int:
        ...

    def get_chapter(self, project_id: int, number: int) -> dict | None:
        ...

    def get_chapters(self, project_id: int) -> list[dict]:
        ...

    def get_last_chapters_content(self, project_id: int, n: int) -> list[dict]:
        ...


# ─── State Engine ─────────────────────────────────────────────────────────────

@runtime_checkable
class StateStore(Protocol):
    """
    Хранилище State Engine.

    Реализуется: db_projects.
    Используется: pipeline, prevalidation, state.py.
    """
    def get_state(self, project_id: int) -> dict:
        ...

    def update_state(
        self,
        project_id: int,
        global_state: str | None,
        plot_matrix: str | None,
        memory_graph: str | None,
    ) -> None:
        ...


# ─── Pipeline Stage ───────────────────────────────────────────────────────────

@runtime_checkable
class PipelineStage(Protocol):
    """
    Один шаг pipeline.

    Реализуется: объекты PipelineStep из pipeline.py.
    Используется: _execute_steps().
    """
    name: str
    enabled: bool


# ─── Narrative Analyzer ───────────────────────────────────────────────────────

@runtime_checkable
class NarrativeAnalyzer(Protocol):
    """
    Анализатор нарративного состояния серии.

    Реализуется: narrative_intelligence.NarrativeIntelligence.
    Используется: web UI, CLI, prevalidation (будущее).
    """
    def analyze(
        self,
        project_id: int,
        through_chapter: int,
        api_call_fn: LLMCaller,
    ) -> "NarrativeReport":
        ...


# ─── Narrative Report (data contract) ────────────────────────────────────────

class NarrativeReport:
    """
    Результат анализа NIL.
    Data-класс без логики — только контракт структуры ответа.
    """
    __slots__ = (
        "project_id",
        "through_chapter",
        "arc_health",          # dict[str, ArcStatus] — персонаж → статус арки
        "promise_status",      # list[PromiseItem] — обещания и их выполнение
        "contradictions",      # list[str] — обнаруженные противоречия
        "mood_trajectory",     # list[str] — тональность по главам
        "conflict_density",    # list[float] — плотность конфликта по главам
        "warnings",            # list[str] — что требует внимания автора
        "ok",                  # bool — нет ли блокирующих проблем
    )

    def __init__(
        self,
        project_id: int,
        through_chapter: int,
        arc_health: dict | None = None,
        promise_status: list | None = None,
        contradictions: list | None = None,
        mood_trajectory: list | None = None,
        conflict_density: list | None = None,
        warnings: list | None = None,
        ok: bool = True,
    ):
        self.project_id       = project_id
        self.through_chapter  = through_chapter
        self.arc_health       = arc_health or {}
        self.promise_status   = promise_status or []
        self.conflict_density = conflict_density or []
        self.mood_trajectory  = mood_trajectory or []
        self.contradictions   = contradictions or []
        self.warnings         = warnings or []
        self.ok               = ok

    def to_dict(self) -> dict:
        return {
            "project_id":       self.project_id,
            "through_chapter":  self.through_chapter,
            "arc_health":       self.arc_health,
            "promise_status":   self.promise_status,
            "contradictions":   self.contradictions,
            "mood_trajectory":  self.mood_trajectory,
            "conflict_density": self.conflict_density,
            "warnings":         self.warnings,
            "ok":               self.ok,
        }


# ─── Вспомогательные типы ─────────────────────────────────────────────────────

class ArcStatus:
    """Статус персонажной арки."""
    __slots__ = ("character", "status", "last_seen_chapter", "evolution_notes", "stalled")

    def __init__(
        self,
        character: str,
        status: str,             # "active" | "stalled" | "resolved" | "unknown"
        last_seen_chapter: int,
        evolution_notes: str = "",
        stalled: bool = False,
    ):
        self.character          = character
        self.status             = status
        self.last_seen_chapter  = last_seen_chapter
        self.evolution_notes    = evolution_notes
        self.stalled            = stalled

    def to_dict(self) -> dict:
        return {
            "character":         self.character,
            "status":            self.status,
            "last_seen_chapter": self.last_seen_chapter,
            "evolution_notes":   self.evolution_notes,
            "stalled":           self.stalled,
        }


class PromiseItem:
    """Одно сюжетное обещание и его статус."""
    __slots__ = ("text", "introduced_chapter", "resolved", "resolved_chapter", "overdue")

    def __init__(
        self,
        text: str,
        introduced_chapter: int,
        resolved: bool = False,
        resolved_chapter: int | None = None,
        overdue: bool = False,
    ):
        self.text               = text
        self.introduced_chapter = introduced_chapter
        self.resolved           = resolved
        self.resolved_chapter   = resolved_chapter
        self.overdue            = overdue

    def to_dict(self) -> dict:
        return {
            "text":               self.text,
            "introduced_chapter": self.introduced_chapter,
            "resolved":           self.resolved,
            "resolved_chapter":   self.resolved_chapter,
            "overdue":            self.overdue,
        }


# ─── TypedDict — структурные контракты данных ────────────────────────────────
# Используются как type hints в build_engine_context, pipeline, chapter_analyzer.
# Дают статическую проверку без ABC-наследования.

from typing import TypedDict


class SummaryDict(TypedDict, total=False):
    """
    Структура одного L3-саммари главы.
    Поля optional (total=False) — старые записи могут не иметь новых полей.
    """
    chapter_num: int
    events: str
    characters: str
    conflicts: str
    promises: str
    mood: str
    raw_summary: str
    created_at: str


class EngineContextDict(TypedDict, total=False):
    """
    Контекст переданный в build_engine_context / _build_context в pipeline.
    Явный контракт вместо произвольного **kwargs.
    """
    genre_text: str
    mode: str                   # "quick" | "quality" | "master"
    model_value: str
    include_dialectics: bool
    task_text: str
    pre_selected_modules: list


class ChapterAnalysisDict(TypedDict, total=False):
    """
    Структура сохранённого ChapterAnalysis (as_dict() → БД → обратно).
    """
    project_id: int
    chapter_num: int
    arc_progress: dict          # {character_name: str}
    character_deltas: list      # list[CharacterDelta.to_dict()]
    opened_promises: list       # list[str]
    closed_promises: list       # list[str]
    causal_chains: list         # list[CausalChain.to_dict()]
    logical_gaps: list          # list[str]
    conflict_score: float
    pacing_note: str
    plot_threads: dict          # {thread_name: status_str}
    analysis_quality: str       # "ok" | "partial" | "failed"


class PipelineResultDict(TypedDict, total=False):
    """
    Структура результата pipeline run.
    Возвращается из start_pipeline() и continue_pipeline().
    """
    run_id: int
    stage: str                  # "generate" | "critique" | "judge" | "done" | "error"
    generated_text: str
    critique: str
    judge_verdict: str
    score: int
    accepted: bool
    iteration: int
    error: str                  # заполняется при stage="error"
    drift_warning: str


# ─── Error Boundary ───────────────────────────────────────────────────────────

@runtime_checkable
class ErrorBoundary(Protocol):
    """
    Централизованная точка обработки ошибок.

    Реализуется: logger.EngineLogger.
    Используется: везде вместо try/except pass.
    """
    def capture(self, context: str, error: Exception, level: str = "error") -> None:
        """Зафиксировать ошибку с контекстом. Никогда не бросает исключение."""
        ...

    def warning(self, context: str, message: str) -> None:
        """Записать предупреждение."""
        ...
