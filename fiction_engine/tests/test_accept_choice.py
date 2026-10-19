"""«Принять»: какой круг принимается — лучший по судье, а не только последний («Фон», 19.10)."""
import pytest


@pytest.fixture
def client(project_id):
    from web.app import app
    from engine.db_settings import set_active_project
    set_active_project(project_id)
    app.config.update(TESTING=True, FE_CSRF=False)
    return app.test_client()


DRAFT, EDITED = "Черновик главы. " * 40, "Правленая глава. " * 40


def _run(project_id, judge="chatgpt_subscription::gpt-6.1-sol@medium"):
    """Глава 10 «Фона»: черновик 32 «ПРИНЯТЬ», после правки 29 «НА ДОРАБОТКУ»."""
    from engine.db_narrative import create_pipeline_run, save_pipeline_iteration
    run = create_pipeline_run(project_id, 1, "w", "c", "w", judge)
    save_pipeline_iteration(run, 1, "generate", "w", "задача", DRAFT)
    save_pipeline_iteration(run, 1, "critique", "c", "", "разбор", 36)
    save_pipeline_iteration(run, 1, "judge", "j", "", "оценка", 32, "ПРИНЯТЬ")
    save_pipeline_iteration(run, 2, "edit", "w", "", EDITED)
    save_pipeline_iteration(run, 2, "continuity_fix", "w", "", EDITED + "Сверено.")
    save_pipeline_iteration(run, 2, "judge", "j", "", "оценка", 29, "НА ДОРАБОТКУ")
    return run


def test_rounds_best_and_text(project_id):
    from engine.db import get_pipeline_iterations
    from engine.pipeline import best_round, pipeline_rounds, round_of_text
    rounds = pipeline_rounds(get_pipeline_iterations(_run(project_id)))
    assert [(r["round"], r["score"], r["verdict"]) for r in rounds] == [(1, 32, "ПРИНЯТЬ"), (2, 29, "НА ДОРАБОТКУ")]
    assert rounds[1]["text"] == EDITED + "Сверено."           # текст круга — последний шаг перед судьёй
    assert best_round(rounds)["round"] == 1
    assert round_of_text(rounds, DRAFT)["round"] == 1 and round_of_text(rounds, "своя правка") is None
    # Переоценка без нового текста судит прежний текст; при равенстве — поздний круг
    rounds.append({"round": 3, "text": rounds[1]["text"], "score": 32, "verdict": "ПРИНЯТЬ"})
    assert best_round(rounds)["round"] == 3
    assert best_round([{"round": 1, "text": "т", "score": None, "verdict": ""}]) is None


def test_rounds_view(project_id, client):
    r = client.get(f"/pipeline/{_run(project_id)}/rounds").get_json()
    assert r["best"] == 1 and r["threshold"] == 30
    assert [(x["round"], x["score"], x["words"]) for x in r["rounds"]] == [(1, 32, 80), (2, 29, 81)]


def test_accept_earlier_round_records_its_score(project_id, client):
    from unittest.mock import patch
    from engine.db_core import get_conn
    run = _run(project_id)
    with patch("web.blueprints.generate_pipeline._start_state_update", return_value=None):
        assert client.post("/pipeline/accept", json={"run_id": run, "chapter_num": 1, "final_text": DRAFT}).get_json()["ok"]
    with get_conn() as conn:
        edit = conn.execute("SELECT action, judge_score FROM author_edits WHERE run_id=?", (run,)).fetchone()
        calib = conn.execute("SELECT judge_score FROM judge_calibration WHERE project_id=?", (project_id,)).fetchone()
    # Принят черновик как есть — это не ручная правка, и оценка его, а не последнего круга
    assert tuple(edit) == ("accept", 32) and calib[0] == 32
