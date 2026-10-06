"""
Находки F5 и F7 первого аудита (AUDIT_UNIFIED.md).

F5: после сохранения главы отказ генерации L3 и авто-оценки гасился без
записи в лог — L3 молча не создавалась, и следующие главы теряли память.
F7: CLI делал int() от ввода и падал на опечатке в номере главы.
"""
from unittest.mock import patch


def test_l3_failure_is_logged(project_id):
    from web.blueprints import helpers
    with patch("engine.pipeline.generate_l3", side_effect=RuntimeError("сеть")), \
         patch.object(helpers, "log_web_error") as log, \
         patch("engine.pipeline.auto_drift_check_if_needed", return_value=None), \
         patch("engine.pipeline.generate_director_note_for_chapter", return_value=None), \
         patch.object(helpers, "_get_scorer_model", return_value=None):
        res = helpers.after_chapter_saved(project_id, 1, "Текст главы. " * 50, "m::x")
    assert res["l3_generated"] is False
    assert any("L3" in c.args[0] for c in log.call_args_list)


def test_auto_score_failure_is_logged(project_id):
    from web.blueprints import helpers
    with patch("engine.db.get_api_key", return_value="k"), \
         patch("engine.pipeline.score_text", side_effect=RuntimeError("сеть")), \
         patch.object(helpers, "log_web_error") as log:
        assert helpers._auto_score_chapter(project_id, 1, "Текст.", "nano_gpt::x") is None
    assert any("авто-оценка" in c.args[0] for c in log.call_args_list)


def test_prompt_int_asks_again_on_typo(capsys):
    import cli
    with patch("builtins.input", side_effect=["пять", "5"]):
        assert cli.prompt_int("Номер главы", 3) == 5
    assert "Нужно число" in capsys.readouterr().out


def test_prompt_int_empty_gives_default():
    import cli
    with patch("builtins.input", side_effect=[""]):
        assert cli.prompt_int("Номер главы", 3) == 3


# ─── F6: обновление State после принятия — в фоне ────────────────────────────

import pytest


@pytest.fixture
def client():
    import logging
    from web.app import app
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    logging.disable(logging.CRITICAL)
    yield app.test_client()
    logging.disable(logging.NOTSET)


def _wait_done(client, job):
    import time
    for _ in range(100):
        s = client.get(f"/pipeline/state_status/{job}").get_json()
        if s["status"] == "done":
            return s
        time.sleep(0.05)
    raise AssertionError("фоновое обновление State не закончилось")


def test_accept_answers_at_once_and_state_updates_in_background(client):
    """Ответ «принять» не ждёт модель; статус State — отдельным запросом."""
    import threading
    from engine.db import create_pipeline_run, create_project, get_chapter, set_active_project
    from web.blueprints import generate_pipeline as gp
    pid = create_project("F6", "детектив")
    set_active_project(pid)
    run_id = create_pipeline_run(pid, 1, "m", "m", "m", "m")
    release = threading.Event()

    def slow_update(project_id, chapter_num, model_value):
        release.wait(5)                     # модель «думает», пока тест не отпустит
        return True

    with patch.object(gp, "_try_state_update_after_accept", side_effect=slow_update):
        r = client.post("/pipeline/accept", json={"run_id": run_id, "chapter_num": 1,
                                                  "final_text": "Глава. " * 50,
                                                  "model_value": "m::x"})
        body = r.get_json()
        assert r.status_code == 200 and body["ok"] and body["state_job"]
        # глава сохранена до того, как State обновился
        assert get_chapter(pid, 1)
        assert client.get(f"/pipeline/state_status/{body['state_job']}").get_json()["status"] == "running"
        release.set()
        assert _wait_done(client, body["state_job"])["state_updated"] is True


def test_state_status_of_other_project_is_hidden(client):
    from engine.db import create_project, set_active_project
    from web.blueprints import generate_pipeline as gp
    a = create_project("A", "детектив")
    b = create_project("B", "детектив")
    with patch.object(gp, "_try_state_update_after_accept", return_value=False):
        job = gp._start_state_update(a, 1, "m::x")
    set_active_project(b)
    assert client.get(f"/pipeline/state_status/{job}").status_code == 404
    assert client.get("/pipeline/state_status/нет-такой").status_code == 404
