"""Мелочи разбора 21.10, пакет 1: данные и маршруты."""
import json


def _client(project_id):
    from engine.db_settings import set_active_project
    from web.app import app
    set_active_project(project_id)
    app.config.update(TESTING=True, FE_CSRF=False)
    return app.test_client()


def test_old_book_recompute_of_last_chapter_is_not_a_before_snapshot(project_id):
    """Снимка до последней главы нет — снимок при её пересчёте не «перед анализом»:
    иначе «Откатить» и State на момент главы вернули бы её прежний текст."""
    from engine.db import save_chapter
    from engine.db_chapters import prepare_chapter_replace
    from engine.db_core import get_conn
    from engine.db_state import (SNAPSHOT_RECOMPUTE, mark_update_applied, save_state_update,
                                 snapshot_before_chapter, update_state)
    from engine.state_merge import merge_analysis_into_state
    save_chapter(project_id, 1, "Глава один. " * 40, "Глава 1")
    update_state(project_id, global_state="## ПЕРСОНАЖИ\n### Вера\nСОСТОЯНИЕ: прежняя глава\n")
    mark_update_applied(project_id, save_state_update(project_id, 1, "{}"))   # глава принята до снимков
    assert prepare_chapter_replace(project_id, 1)["state_stale"] is True
    analysis = {"global_state_changes": [{"name": "Вера", "состояние": "новая глава"}]}
    merge_analysis_into_state(project_id, json.dumps(analysis, ensure_ascii=False), 1)
    with get_conn() as conn:
        reasons = [r[0] for r in conn.execute("SELECT reason FROM state_history WHERE project_id=?", (project_id,))]
    assert f"{SNAPSHOT_RECOMPUTE}1" in reasons and snapshot_before_chapter(project_id, 1) is None


def test_loaded_chapter_recompute_is_not_stale(project_id):
    """Загруженная глава, анализ которой в State ещё не вливался: снимка до неё нет,
    но и следов прежнего текста в State нет — предупреждать не о чем (25.10)."""
    from engine.db import save_chapter
    from engine.db_chapters import prepare_chapter_replace
    save_chapter(project_id, 1, "Глава один. " * 40, "Глава 1")
    assert prepare_chapter_replace(project_id, 1)["state_stale"] is False


def test_project_forms_carry_project_guard(project_id):
    """Жанр и стиль — проверка вкладки; новый / переключить / удалить — без неё."""
    html = _client(project_id).get("/").get_data(as_text=True)
    assert r"/^\/project\/(new|\d+\/(switch|delete))(\/|\?|$)/" in html


def test_delete_other_project_keeps_active(project_id):
    from engine.db_projects import create_project
    from engine.db_settings import get_active_project_id
    c = _client(project_id)
    other = create_project("Другая", "детектив")
    c.post(f"/project/{other}/delete")
    assert str(get_active_project_id()) == str(project_id)
    assert c.post("/project/99999/switch").status_code == 302 and str(get_active_project_id()) == str(project_id)


def test_state_rollback_success_is_200(project_id):
    from engine.db_core import get_conn
    from engine.db_state import update_state
    update_state(project_id, global_state="раз", _snapshot_reason="ручной")
    update_state(project_id, global_state="два")
    with get_conn() as conn:
        sid = conn.execute("SELECT id FROM state_history WHERE project_id=? ORDER BY id LIMIT 1",
                           (project_id,)).fetchone()[0]
    c = _client(project_id)
    rules = [r for r in c.application.url_map.iter_rules() if "restore" in r.rule and "state" in r.rule]
    assert rules
    url = rules[0].rule.replace("<int:snapshot_id>", str(sid)).replace("<int:sid>", str(sid))
    assert c.post(url, json={"snapshot_id": sid}).status_code == 200


def test_accept_takes_chapter_from_run_and_keeps_title(project_id, monkeypatch):
    from engine.db import get_chapter, save_chapter
    from engine.db_narrative import create_pipeline_run
    from web.blueprints import generate_pipeline
    save_chapter(project_id, 2, "Старый текст. " * 40, "Мост")
    run = create_pipeline_run(project_id, 2, "w::x", "c::x", "w::x", "j::x")
    monkeypatch.setattr(generate_pipeline, "_start_state_update", lambda *a, **k: "job")
    r = _client(project_id).post("/pipeline/accept", json={"run_id": run, "chapter_num": 5,
                                                           "final_text": "Новый текст. " * 40, "model_value": "w::x"})
    assert r.status_code == 200
    ch = get_chapter(project_id, 2)
    assert ch["title"] == "Мост" and ch["content"].startswith("Новый") and not get_chapter(project_id, 5)


def test_local_time_filter():
    from web.app import local_time
    assert len(local_time("2026-10-21 10:51:00")) == 16
    assert local_time("не время") == "не время"
