"""
db.py — слой обратной совместимости.

Весь код импортирует из этого файла — ничего не ломается.
Реальная логика разделена на три слоя:
  db_core.py     — соединение, схема, миграции
  db_settings.py — ключи, настройки, prep
  db_projects.py — проекты, главы, state, память, pipeline, KB

Добавляя новые функции — добавляй их в нужный слой,
а здесь только переэкспортируй.
"""

# ─── Инфраструктура ───────────────────────────────────────────────────────────
from .db_core import (
    DB_PATH,
    get_conn,
    init_db,
    log_error,
    get_error_log,
    _default_global,
    _default_plot,
    _default_memory,
)

# ─── Конфигурация ─────────────────────────────────────────────────────────────
from .db_settings import (
    save_api_key,
    get_api_key,
    get_all_api_keys,
    get_setting,
    set_setting,
    get_active_project_id,
    set_active_project,
    PREP_SECTIONS,
    PREP_DEFAULTS,
    get_prep,
    save_prep,
    get_prep_context,
)

# ─── Данные проектов ──────────────────────────────────────────────────────────
from .db_projects import (
    # Проекты
    create_project,
    get_projects,
    get_project,
    delete_project,
    # Главы
    save_chapter,
    get_chapter,
    get_chapters,
    get_last_chapters_content,
    # State Engine
    get_state,
    update_state,
    save_state_update,
    mark_update_applied,
    get_pending_updates,
    get_last_update,
    parse_structured_state,
    parse_structured_state_smart,
    get_structured_state,
    merge_analysis_into_state,
    # Генерации
    save_generation_score,
    save_chapter_score,
    get_generation_history,
    get_generation_by_id,
    # Символы
    get_symbols,
    save_symbol,
    add_symbol_appearance,
    add_symbol_planned,
    delete_symbol,
    get_symbols_context,
    # Голосовые профили
    get_voice_profiles,
    save_voice_profile,
    set_active_voice,
    get_active_voice,
    delete_voice_profile,
    # Pipeline
    create_pipeline_run,
    save_pipeline_iteration,
    get_pipeline_run,
    get_pipeline_iterations,
    finish_pipeline_run,
    get_pipeline_runs,
    # Drift
    save_drift_check,
    get_last_drift_check,
    should_run_drift_check,
    # L3 Memory
    save_l3_summary,
    get_l3_summaries,
    get_l3_summary,
    delete_l3_summary,
    get_l3_status,
    get_l3_active_promises,   # новая функция — связь с prevalidation
    # Режиссёрские заметки
    save_director_note,
    get_director_note,
    # Эталоны
    save_exemplar,
    get_exemplars,
    delete_exemplar,
    # State History
    snapshot_state,
    get_state_history,
    restore_state_snapshot,
    # База знаний
    kb_get_all,
    kb_get,
    kb_save,
    kb_delete,
    kb_search,
    kb_get_auto_inject,
    # Заглушки (обратная совместимость)
    init_generation_history,
    init_symbol_tables,
    init_voice_tables,
    init_pipeline_tables,
    init_voice_drift_table,
    init_l3_memory,
)

from .db_chapters import (
    # Chapter Analysis (когнитивный слой)
    save_chapter_analysis,
    get_chapter_analysis,
    get_analyses_range,
    get_all_logical_gaps,
    # Score history (пункт 3: judge calibration)
    get_judge_score_history,
    format_score_history,
    # Author edits / DATA_DRIVEN_LEARNING (пункт 2)
    save_author_edit,
    get_author_edit_patterns,
    # Structural monotony detection (пункт 6)
    check_structural_monotony,
    # Eval / calibration layer
    save_judge_calibration,
    get_judge_calibration_hint,
)

__all__ = [
    # Перечислено неявно через import * из трёх слоёв выше.
    # Явный __all__ не нужен — все имена уже в пространстве модуля.
]


def get_api_keys_dict() -> dict:
    """
    Публичная функция для получения всех API-ключей в виде словаря.
    Используй вместо приватного pipeline._get_keys() в scene_editor и voice_profiles.
    """
    return {
        "anthropic": get_api_key("anthropic_direct"),
        "nano":      get_api_key("nano_gpt"),
        "openai":    get_api_key("openai_direct"),
        "gemini":    get_api_key("gemini_direct"),
        "deepseek":  get_api_key("deepseek_direct"),
    }
