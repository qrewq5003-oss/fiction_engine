"""
db_projects.py — фасад обратной совместимости.

Собственная ответственность: CRUD проектов.
Всё остальное делегировано специализированным модулям:
  - db_chapters.py  — главы, история генераций, анализ
  - db_state.py     — State Engine, парсинг, слияние
  - db_narrative.py — символы, голос, L3, pipeline, KB, эталоны, заметки
"""

from .db_core import get_conn, _default_global, _default_plot, _default_memory
from .error_policy import handle_error, ErrorLevel

# Реэкспорт для обратной совместимости
from .db_chapters import (
    save_chapter, get_chapter, get_chapters, get_last_chapters_content,
    save_generation_score, save_chapter_score,
    get_generation_history, get_generation_by_id,
    save_chapter_analysis, get_chapter_analysis,
    get_analyses_range, get_all_logical_gaps,
    init_generation_history,
)
from .db_state import (
    get_state, update_state, save_state_update, mark_update_applied,
    get_pending_updates, get_last_update,
    snapshot_state, get_state_history, restore_state_snapshot,
    parse_structured_state, parse_structured_state_smart, get_structured_state, merge_analysis_into_state,
)
from .db_narrative import (
    get_symbols, save_symbol, add_symbol_appearance, add_symbol_planned,
    delete_symbol, get_symbols_context, init_symbol_tables,
    get_voice_profiles, save_voice_profile, set_active_voice,
    get_active_voice, delete_voice_profile, init_voice_tables,
    save_l3_summary, get_l3_summaries, get_l3_summary, delete_l3_summary,
    get_l3_status, get_l3_active_promises, init_l3_memory,
    save_drift_check, get_last_drift_check, should_run_drift_check,
    init_voice_drift_table,
    create_pipeline_run, save_pipeline_iteration, get_pipeline_run,
    get_pipeline_iterations, finish_pipeline_run, get_pipeline_runs,
    init_pipeline_tables,
    save_director_note, get_director_note,
    save_exemplar, get_exemplars, delete_exemplar,
    kb_get_all, kb_get, kb_save, kb_delete, kb_search, kb_get_auto_inject,
)


# ─── Проекты ─────────────────────────────────────────────────────────────────

def create_project(name: str, genre: str = "") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO projects (name, genre) VALUES (?, ?)", (name, genre)
        )
        project_id = cur.lastrowid
        conn.execute(
            "INSERT INTO state_engine (project_id, global_state, plot_matrix, memory_graph) VALUES (?,?,?,?)",
            (project_id, _default_global(), _default_plot(), _default_memory())
        )
        return project_id


def get_projects():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT p.*, (SELECT MAX(number) FROM chapters WHERE project_id=p.id) as last_chapter "
            "FROM projects p ORDER BY p.created_at DESC"
        ).fetchall()]


def get_project(project_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return dict(row) if row else None


def delete_project(project_id: int):
    """
    Удалить проект и все его данные.

    Список подчинённых таблиц строится из схемы (`project_scoped_tables`),
    а не задаётся вручную: захардкоженный перечень отставал от схемы и
    оставлял осиротевшие строки в state_engine, l3_memory, chapter_analysis
    и ещё восьми таблицах.
    """
    from .db_core import project_scoped_tables
    with get_conn() as conn:
        for table in project_scoped_tables(conn):
            if table == "projects":
                continue
            try:
                conn.execute(f"DELETE FROM {table} WHERE project_id=?", (project_id,))
            except Exception as e:
                handle_error(f"delete_project({project_id}) table={table}", e,
                             level=ErrorLevel.RECOVERABLE)
        conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
        row = conn.execute("SELECT value FROM settings WHERE key='active_project'").fetchone()
        if row and row["value"] == str(project_id):
            conn.execute("DELETE FROM settings WHERE key='active_project'")


def _empty_structured_state(state: dict) -> dict:
    return {"characters": {}, "char_names": [], "world": {}, "plot": {}, "raw": state}
