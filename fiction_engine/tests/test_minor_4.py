"""Мелочи разбора 21.10, пакет 4: интерфейс, маршруты, данные."""
import threading


def _client(project_id):
    from engine.db_settings import set_active_project
    from web.app import app
    set_active_project(project_id)
    app.config.update(TESTING=True, FE_CSRF=False)
    return app.test_client()


def test_menu_counts_pending_analyses(project_id):
    from engine.db_state import save_state_update
    save_state_update(project_id, 1, "{}")
    html = _client(project_id).get("/").get_data(as_text=True)
    assert '<span class="badge-count">1</span>' in html


def test_stats_shows_background_errors(project_id):
    from engine.db_core import log_error
    log_error("после сохранения: память L3", RuntimeError("модель молчит"))
    html = _client(project_id).get("/stats").get_data(as_text=True)
    assert "Сбои фоновых шагов" in html and "модель молчит" in html


def test_stale_cleanup_spares_running_round(project_id):
    from engine.db import get_pipeline_run
    from engine.db_core import get_conn
    from engine.db_narrative import create_pipeline_run
    from engine.pipeline import ACTIVE_RUNS
    live, dead = (create_pipeline_run(project_id, n, "w::x", "c::x", "w::x", "j::x") for n in (1, 2))
    with get_conn() as conn:
        conn.execute("UPDATE pipeline_runs SET created_at=datetime('now','-3 hours') WHERE id IN (?,?)", (live, dead))
    ACTIVE_RUNS.add(live)
    try:
        r = _client(project_id).post("/pipeline/cleanup").get_json()
    finally:
        ACTIVE_RUNS.discard(live)
    assert r["cleaned"] == 1
    assert get_pipeline_run(live)["status"] == "running" and get_pipeline_run(dead)["status"] == "rejected"


def test_usage_is_per_thread():
    from engine.api import _remember_usage, get_last_usage, set_current_operation, get_current_operation
    _remember_usage(10, 20)
    set_current_operation("критик")
    seen = {}

    def other():
        seen["usage"], seen["op"] = get_last_usage(), get_current_operation()
        _remember_usage(1, 1)
    t = threading.Thread(target=other)
    t.start()
    t.join()
    assert seen == {"usage": {}, "op": ""}
    assert get_last_usage()["output_tokens"] == 20 and get_current_operation() == "критик"
