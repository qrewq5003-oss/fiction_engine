"""Мелочи разбора 21.10: гонка после «Принять», «Идеи», «Отклонить», статус анализа State."""
import threading

TEXT = "Принятая глава. " * 40


def _client(project_id):
    from engine.db_settings import set_active_project
    from web.app import app
    set_active_project(project_id)
    app.config.update(TESTING=True, FE_CSRF=False)
    return app.test_client()


def test_rollback_during_accept_processing(project_id, monkeypatch):
    """Главу откатили, пока шла обработка «Принять», — State не вливается, записанное убирается."""
    from engine import db_chapters
    from engine.db import get_chapter, save_chapter
    from web.blueprints import generate_pipeline, helpers
    save_chapter(project_id, 3, TEXT, "Глава 3")
    seen, forgot = [], []
    done = threading.Event()

    def analysis_then_rollback(pid, n, model, alive=None, on_fail=None):
        # Пока шёл анализ, автор нажал «Откатить»
        with db_chapters.get_conn() as conn:
            conn.execute("DELETE FROM chapters WHERE project_id=? AND number=?", (pid, n))
        seen.append(("alive после отката", alive()))
        return False
    monkeypatch.setattr(generate_pipeline, "_try_state_update_after_accept", analysis_then_rollback)
    monkeypatch.setattr(helpers, "after_chapter_saved", lambda *a, **k: seen.append("L3 и прочее"))
    monkeypatch.setattr("engine.pipeline.record_accepted_analysis", lambda *a, **k: seen.append("анализ"))
    real_forget = db_chapters.forget_chapter_text

    def forget(pid, n):
        forgot.append(n)
        r = real_forget(pid, n)
        done.set()
        return r
    monkeypatch.setattr(db_chapters, "forget_chapter_text", forget)
    generate_pipeline._start_state_update(project_id, 3, "w", TEXT)
    assert done.wait(10)
    assert seen == [("alive после отката", False)] and forgot == [3] and get_chapter(project_id, 3) is None


def test_after_chapter_saved_stops_when_chapter_gone(project_id, monkeypatch):
    from web.blueprints.helpers import after_chapter_saved
    calls = []
    monkeypatch.setattr("engine.pipeline.generate_l3", lambda *a, **k: calls.append("l3"))
    assert after_chapter_saved(project_id, 3, TEXT, "w", alive=lambda: False) == {"failed": []} and not calls


def test_ideas_to_state_is_preview_only(project_id, monkeypatch):
    """«Идеи → в State»: разбор только показывается; записывает «Применить»."""
    from engine.db import get_state, save_chapter
    from engine.db_state import update_state
    update_state(project_id, global_state="## ПЕРСОНАЖИ\n### Вера\nСОСТОЯНИЕ: на смене\n")
    save_chapter(project_id, 1, TEXT, "Глава 1")
    monkeypatch.setattr("engine.pipeline.call_json", lambda *a, **k: {
        "global_state": "## ПЕРСОНАЖИ\n### Иной", "plot_matrix": "## ОСНОВНАЯ ЛИНИЯ\nиное", "memory_graph": ""})
    monkeypatch.setenv("NANO_GPT_API_KEY", "test-key")
    r = _client(project_id).post("/ideas/accept", json={"text": "идеи", "model": "nano_gpt::x/y",
                                                       "action": "state"}).get_json()
    assert r["ok"] and r["chapters"] == 1 and "на смене" in get_state(project_id)["global_state"]


def test_ideas_new_project_cards_go_to_prep(project_id, monkeypatch):
    from engine.db import get_state
    from engine.db_settings import get_prep
    monkeypatch.setattr("engine.pipeline.call_json", lambda *a, **k: {
        "project_name": "Смена", "global_state": "## ПЕРСОНАЖИ\n### Вера", "plot_matrix": "## ОСНОВНАЯ ЛИНИЯ\nсмерть",
        "memory_graph": "## КЛЮЧЕВЫЕ СОБЫТИЯ\n- ночь"})
    monkeypatch.setenv("NANO_GPT_API_KEY", "test-key")
    r = _client(project_id).post("/ideas/accept", json={"text": "идеи", "model": "nano_gpt::x/y",
                                                       "action": "project"}).get_json()
    pid = r["project_id"]
    prep = get_prep(pid)
    assert "### Вера" in prep["characters"] and "смерть" in prep["plot"]
    st = get_state(pid)
    assert "### Вера" not in st["global_state"] and "ночь" in st["memory_graph"]


def test_reject_records_author_edit(project_id):
    from engine.db import get_conn
    from engine.db_narrative import create_pipeline_run, save_pipeline_iteration
    run = create_pipeline_run(project_id, 4, "w", "c", "w", "j")
    save_pipeline_iteration(run, 1, "generate", "w", "задача", TEXT)
    assert _client(project_id).post("/pipeline/reject", json={"run_id": run}).get_json()["ok"]
    with get_conn() as conn:
        row = conn.execute("SELECT chapter_num, action FROM author_edits WHERE run_id=?", (run,)).fetchone()
    assert row and row["chapter_num"] == 4 and row["action"] == "reject"


def test_state_analyze_status_is_per_project(project_id):
    from engine.db_projects import create_project
    from web.blueprints import state_bp
    with state_bp._analyze_lock:
        state_bp._analyze_jobs["job-x"] = {"status": "done", "result": {"ok": 1}, "error": None,
                                           "project_id": project_id}
    c = _client(project_id)
    assert c.get("/state/analyze/status/job-x").status_code == 200
    from engine.db_settings import set_active_project
    set_active_project(create_project("Другой", "детектив"))
    assert c.get("/state/analyze/status/job-x").status_code == 404


def test_request_for_other_project_is_refused(project_id):
    """X-FE-Project не совпадает с открытым проектом — 409; совпадает или нет заголовка — как раньше."""
    from engine.db_projects import create_project
    c = _client(project_id)
    assert c.get("/api/voice/active", headers={"X-FE-Project": str(project_id)}).status_code == 200
    other = create_project("Другая книга", "детектив")
    r = c.post("/voice/save", json={"name": "чужой", "profile": "профиль"}, headers={"X-FE-Project": str(other)})
    assert r.status_code == 409 and r.get_json()["project_mismatch"]
    assert c.get("/api/voice/active").status_code == 200
