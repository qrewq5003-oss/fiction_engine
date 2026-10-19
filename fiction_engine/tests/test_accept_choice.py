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


def _r(n, score, plan, verdict="ПРИНЯТЬ"):
    return {"round": n, "text": f"т{n}", "score": score, "verdict": verdict,
            "plan": None if plan is None else {"missing": plan[0], "partial": plan[1]}}


def test_best_round_prefers_closed_plan_within_slack():
    from engine.pipeline import best_round
    # Дымовая книга, гл.1: 33 с двумя «частично» против 31 с планом целиком
    assert best_round([_r(1, 33, (0, 2)), _r(2, 31, (0, 0))])["round"] == 2
    assert best_round([_r(1, 33, (0, 2)), _r(2, 30, (0, 0))])["round"] == 1     # дальше уступки
    assert best_round([_r(1, 33, None), _r(2, 31, (0, 0))])["round"] == 1       # лучший не сверен
    assert best_round([_r(1, 33, (0, 2)), _r(2, 32, None)])["round"] == 1       # другой не сверен
    assert best_round([_r(1, 33, (0, 2)), _r(2, 32, (0, 0), "НА ДОРАБОТКУ")])["round"] == 1
    # «нет» тяжелее любого числа «частично»
    assert best_round([_r(1, 33, (1, 0)), _r(2, 32, (0, 3))])["round"] == 2
    assert best_round([_r(1, 33, (0, 1)), _r(2, 32, (1, 0))])["round"] == 1


def test_plan_check_saved_per_round_text(project_id, client):
    from unittest.mock import patch
    run = _run(project_id)
    items = [{"n": 1, "item": "СЦЕНА 1: встреча", "status": "есть", "quote": "", "quote_ok": True, "note": ""},
             {"n": 2, "item": "СЦЕНА 2: ссора", "status": "частично", "quote": "", "quote_ok": True, "note": ""}]
    from engine.db import save_director_note
    save_director_note(project_id, 0, "СЦЕНА 1: встреча\nСЦЕНА 2: ссора")
    with patch("engine.plan_check.check_plan", return_value=items), \
         patch("engine.plan_check.plan_checker_model", return_value=("chatgpt_subscription::gpt-6.1-sol", "")):
        r = client.post("/pipeline/plan_check", json={"chapter_num": 1, "text": DRAFT, "run_id": run}).get_json()
    assert r["ok"]
    rounds = client.get(f"/pipeline/{run}/rounds").get_json()["rounds"]
    assert rounds[0]["plan"] == {"missing": 0, "partial": 1} and rounds[1]["plan"] is None
    # Сверка остаётся у запуска, пока его не удалят вместе с историей
    assert client.post("/pipeline/delete-history", json={}).get_json()["ok"]


def test_project_with_round_checks_deletes(project_id):
    from engine.db_projects import delete_project, get_project
    from engine.plan_check import save_round_check
    save_round_check(_run(project_id), DRAFT, [{"status": "нет"}, {"status": "есть"}])
    delete_project(project_id)
    assert get_project(project_id) is None
