"""Интерфейс, который держал устаревшее (разбор 21.10, пакет 5)."""
PLAN = "ПЛАН ГЛАВЫ 3\nСЦЕНА 1: Морг\nПОКА НЕ РАСКРЫВАТЬ:\n- кто сделал укол"
CONT = "⚠️ РЕЖИМ: ПРОДОЛЖЕНИЕ ГЛАВЫ — СТРОГИЕ ИНСТРУКЦИИ\n\nКОНЕЦ ПЕРВОЙ ЧАСТИ:\n\nхвост"


def _client(project_id):
    from engine.db_settings import set_active_project
    from web.app import app
    set_active_project(project_id)
    app.config.update(TESTING=True, FE_CSRF=False)
    return app.test_client()


def test_continue_keeps_chapter_plan(project_id):
    """«Продолжить главу» затирала план главы и «пока не раскрывать» — теперь дописывает к нему."""
    from engine.db import get_director_note, save_director_note
    save_director_note(project_id, 2, PLAN)
    c = _client(project_id)
    assert c.post("/api/director_note/3/save", json={"note": CONT, "continue": True}).get_json()["ok"]
    assert c.post("/api/director_note/3/save", json={"note": CONT.replace("хвост", "хвост 2"),
                                                     "continue": True}).get_json()["ok"]
    note = get_director_note(project_id, 3)
    assert note.startswith(PLAN) and "кто сделал укол" in note
    assert note.count("РЕЖИМ: ПРОДОЛЖЕНИЕ") == 1 and "хвост 2" in note


def test_accept_drops_continuation(project_id):
    from engine.db import get_director_note, save_director_note
    from engine.db_narrative import add_continuation, drop_continuation
    save_director_note(project_id, 2, PLAN)
    add_continuation(project_id, 3, CONT)
    assert drop_continuation(project_id, 3) is True and get_director_note(project_id, 3) == PLAN
    assert drop_continuation(project_id, 3) is False
    add_continuation(project_id, 4, CONT)                 # без плана — заметка уходит целиком
    assert drop_continuation(project_id, 4) is True and get_director_note(project_id, 4) is None


def test_accept_route_drops_continuation(project_id, monkeypatch):
    from engine.db import get_director_note, save_director_note
    from engine.db_narrative import add_continuation, create_pipeline_run
    from web.blueprints import generate_pipeline
    save_director_note(project_id, 0, "ПЛАН ГЛАВЫ 1")
    add_continuation(project_id, 1, CONT)
    monkeypatch.setattr(generate_pipeline, "_start_state_update", lambda *a, **k: "job")
    run = create_pipeline_run(project_id, 1, "w", "c", "w", "j")
    r = _client(project_id).post("/pipeline/accept", json={"run_id": run, "chapter_num": 1,
                                                           "final_text": "Глава. " * 50, "model_value": "w"})
    assert r.status_code == 200 and get_director_note(project_id, 1) == "ПЛАН ГЛАВЫ 1"


def test_workshop_fields_are_per_project(project_id):
    """Поля «Мастерской» — под ключом проекта; номер главы не восстанавливается."""
    html = _client(project_id).get("/pipeline").get_data(as_text=True)
    assert f"'fe:{project_id}:' + location.pathname" in html
    assert 'id="pl-chapter" min="1" data-nopersist' in html
