"""Судейская часть по решениям автора 21.10: запас ролей, «ГРУБО» редактору,
авто-оценка, правила оценки запуска, сбой критика или судьи."""
from unittest.mock import patch

JUDGE_OK = ("ГОЛОС: 8\nСТРУКТУРА: 7\nПЕРСОНАЖИ: 8\nСЦЕНЫ: 7\nДИАЛОГ: 8\nИТОГ: 38\n"
            "СВЯЗНОСТЬ: ОК — нет\nОСТАТОК: финал торопится\nВЕРДИКТ: ПРИНЯТЬ")


def test_reserve_set_takes_judge_of_other_family(monkeypatch):
    from engine import pipeline_config as pc
    monkeypatch.setattr(pc, "active_role_preset", lambda: "")
    monkeypatch.setenv("FE_CLAUDE_SUBSCRIPTION", "0")
    monkeypatch.setenv("FE_CHATGPT_SUBSCRIPTION", "0")
    monkeypatch.setattr(pc, "_has_key", lambda m: m.startswith("openai_direct::"))
    roles = pc.default_role_models()
    assert pc.model_family(roles["judge"]) != pc.model_family(roles["gen"])
    monkeypatch.setattr(pc, "_has_key", lambda m: False)        # нет ключа — как было, запуск скажет
    assert pc.default_role_models()["judge"] == pc.DEFAULT_ROLE_MODELS["judge"]


def test_editor_gets_only_rough_confirmed_by_judge(project_id):
    from engine.db import save_pipeline_iteration
    from engine.db_narrative import create_pipeline_run
    from engine.pipeline_steps import _rough_lines
    run = create_pipeline_run(project_id, 1, "w::x", "c::x", "w::x", "j::x")
    critique = "СВЯЗНОСТЬ: ГРУБО — «Вера одна в палате»"
    save_pipeline_iteration(run, 1, "judge", "j::x", "", "СВЯЗНОСТЬ: ЕСТЬ — мелочь", score=34)
    assert _rough_lines(run, 2, critique) == []                 # судья снизил до ЕСТЬ
    save_pipeline_iteration(run, 2, "judge", "j::x", "", "СВЯЗНОСТЬ: ГРУБО — «кто вошёл»", score=30)
    lines = _rough_lines(run, 3, critique)
    assert any("кто вошёл" in x for x in lines) and any("одна в палате" in x for x in lines)


def test_run_keeps_its_rubric(project_id):
    from engine.db import get_pipeline_run, set_setting
    from engine.db_narrative import create_pipeline_run
    from engine.judge_rubric import RUBRIC_KEY, RUN_RUBRIC, rubric
    set_setting(RUBRIC_KEY, "v1")
    run = create_pipeline_run(project_id, 1, "w::x", "c::x", "w::x", "j::x")
    assert get_pipeline_run(run)["rubric"] == "v1"
    set_setting(RUBRIC_KEY, "v2")
    seen = []
    from engine import pipeline
    with patch.object(pipeline, "_execute_steps", lambda **k: seen.append(rubric()) or {}):
        pipeline.run_pipeline_step(run, 2, project_id, 1, "задача", "w::x", "c::x", "w::x", "j::x")
    assert seen == ["v1"] and rubric() == "v2" and RUN_RUBRIC.get() == ""


def test_judge_failure_is_round_without_score(project_id):
    from engine import pipeline
    from engine.pipeline import PipelineStep
    def boom(*a, **k):
        raise RuntimeError("codex: соединение сброшено")
    with patch("engine.pipeline.step_judge", side_effect=boom), \
         patch("engine.pipeline.step_critique", side_effect=boom):
        res = pipeline._execute_steps(steps=[PipelineStep("critique"), PipelineStep("judge")], run_id=0,
                                      iteration=1, project_id=project_id, chapter_num=1,
                                      generation_prompt="задача", model_gen="w::x", model_critic="c::x",
                                      model_editor="w::x", model_judge="j::x",
                                      previous_text="Глава. " * 50, previous_critique="")
    assert "судья не ответил" in res["judge_error"] and "критик не ответил" in res["critique_error"]
    assert not res.get("judge_score")


def test_auto_score_is_judge_of_accepted_round(project_id, monkeypatch):
    from engine.db import save_pipeline_iteration
    from engine.db_core import get_conn
    from engine.db_narrative import create_pipeline_run
    from web.blueprints.helpers import after_chapter_saved
    text = "Принятая глава. " * 60
    run = create_pipeline_run(project_id, 1, "w::x", "c::x", "w::x", "j::x")
    save_pipeline_iteration(run, 1, "generate", "w::x", "задача", text)
    save_pipeline_iteration(run, 1, "judge", "j::x", "", JUDGE_OK, score=38, verdict="ПРИНЯТЬ")
    for name in ("generate_l3", "auto_drift_check_if_needed", "generate_director_note_for_chapter"):
        monkeypatch.setattr(f"engine.pipeline.{name}", lambda *a, **k: None)
    monkeypatch.setattr("engine.pipeline.score_text", lambda *a, **k: (_ for _ in ()).throw(AssertionError("лишний вызов")))
    out = after_chapter_saved(project_id, 1, text, "w::x", run_id=run)
    assert out["auto_score"] == 38
    with get_conn() as conn:
        import json
        d = json.loads(conn.execute("SELECT details FROM chapter_scores WHERE project_id=?", (project_id,)).fetchone()[0])
    assert d["voice"] == 8 and d["source"] == "судья, круг 1" and d["main_issue"].startswith("финал")


def test_quality_graph_uses_current_format(project_id):
    from engine.db import save_chapter_score
    from engine.db_settings import set_active_project
    from web.app import app
    save_chapter_score(project_id, 1, {"voice": 8, "structure": 7, "characters": 8, "scenes": 7, "dialog": 8,
                                       "total": 38, "verdict": "ПРИНЯТЬ", "source": "судья, круг 1"})
    set_active_project(project_id)
    s = app.test_client().get("/api/quality/graph").get_json()["scores"][0]
    assert s["total"] == 38 and s["voice"] == 8 and s["source"] == "судья, круг 1"
