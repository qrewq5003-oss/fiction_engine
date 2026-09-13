"""
fiction_engine.engine — публичный API пакета.

Импортируй отсюда — не из конкретных модулей напрямую.
Это позволит переносить код между модулями без изменения внешних импортов.

Быстрый старт:
    from fiction_engine.engine import (
        init_db,
        start_pipeline, continue_pipeline,
        get_logger,
        STANDARD, QUICK, DEEP,
        analyze_narrative, get_narrative_metrics,
        NarrativeReport,
    )
"""

# ─── Версия ───────────────────────────────────────────────────────────────────
#
# Значение живёт в pyproject.toml. Дублировать его в коде значит однажды
# разойтись, поэтому читаем метаданные установленного пакета. Если пакет
# не установлен (запуск из исходников без `pip install -e .`), отдаём
# "0.0.0+src" — это видно и не притворяется релизом.

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("fiction-engine")
except PackageNotFoundError:            # запуск из исходников
    __version__ = "0.0.0+src"

# ─── Инфраструктура ───────────────────────────────────────────────────────────
from .db_core import init_db, get_conn
from .logger import get_logger, log_error

# ─── Конфигурация ─────────────────────────────────────────────────────────────
from .db_settings import (
    get_api_key, save_api_key,
    get_active_project_id, set_active_project,
    get_prep_context,
)

# ─── Данные проектов ──────────────────────────────────────────────────────────
from .db_projects import (
    create_project, get_projects, get_project, delete_project,
    save_chapter, get_chapter, get_chapters,
    get_state, update_state,
    get_l3_summaries, save_l3_summary, get_l3_active_promises,
)

# ─── Pipeline ─────────────────────────────────────────────────────────────────
from .pipeline import (
    start_pipeline,
    continue_pipeline,
    accept_pipeline,
    reject_pipeline,
    check_voice_drift,
    PipelineStep,
    DEFAULT_PIPELINE,
    PIPELINE_WITH_EDIT,
    PIPELINE_GENERATE_AND_EDIT,
    PIPELINE_WITH_PREVALIDATE,
)
from .pipeline_config import (
    PipelineConfig, StepConfig,
    QUICK, STANDARD, DEEP, CRITIQUE_ONLY, CONTINUE,
    get_preset, list_presets,
)

# ─── Narrative Intelligence ───────────────────────────────────────────────────
from .narrative_intelligence import (
    NarrativeIntelligence,
    analyze_narrative,
    get_narrative_metrics,
    get_nil,
)

# ─── L3 Memory ────────────────────────────────────────────────────────────────
from .l3_memory import generate_l3_summary, get_l3_context

# ─── Cognitive Memory ─────────────────────────────────────────────────────────
from .cognitive_memory import (
    get_cognitive_context,
    get_weighted_promises,
    memory_score_report,
    MemoryField,
    MEMORY_FIELDS,
)

# ─── Chapter Analyzer (интеллектуальный анализ) ───────────────────────────────
from .chapter_analyzer import (
    ChapterAnalyzer,
    ChapterAnalysis,
    CharacterDelta,
    CausalChain,
    analyze_chapter_deep,
    format_analysis_for_prompt,
    get_analyzer,
)

# ─── Error Policy ─────────────────────────────────────────────────────────────
from .error_policy import (
    ErrorLevel,
    ErrorPolicy,
    PipelineError,
    error_boundary,
    handle_error,
)

# ─── Contracts & TypedDict ────────────────────────────────────────────────────
from .contracts import (
    NarrativeReport, ArcStatus, PromiseItem,
    SummaryDict, EngineContextDict, ChapterAnalysisDict, PipelineResultDict,
    LLMCaller, FullModelCaller, SummaryStore, ChapterStore, StateStore,
    PipelineStage, NarrativeAnalyzer, ErrorBoundary,
)

# ─── Валидация + State ────────────────────────────────────────────────────────
from .prevalidation import prevalidate_chapter
from .state import analyze_chapter, build_prompt
