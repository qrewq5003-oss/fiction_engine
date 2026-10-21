"""Роли другой семьи, чем писатель (разбор 21.10, пакет 3): оценщик, проверка непрерывности, судья без «КАЛИБРОВКИ»."""
SONNET = "claude_subscription::claude-sonnet-5-5"
SOL = "chatgpt_subscription::gpt-6.1-sol@medium"


def _set(key, value):
    from engine.db import set_setting
    set_setting(key, value)


def test_scorer_is_never_the_writers_family(project_id, monkeypatch):
    from engine import plan_check
    from engine.pipeline_config import scorer_model_for
    _set("scorer_model", SOL)
    assert scorer_model_for(SONNET) == SOL
    # Оценщик той же семьи (или не задан) — проверяющий другой семьи; нет такого — оценки нет
    monkeypatch.setattr(plan_check, "plan_checker_model", lambda w: (SOL, "") if w == SONNET else ("", "нет"))
    _set("scorer_model", SONNET)
    assert scorer_model_for(SONNET) == SOL
    _set("scorer_model", "")
    assert scorer_model_for(SONNET) == SOL and scorer_model_for(SOL) == ""


def test_score_verdict_uses_scorers_threshold(monkeypatch):
    """Порог оценщика — как у судьи: Sol 31 при своём пороге 30 — «ПРИНЯТЬ» (был общий 35)."""
    from engine import pipeline_tasks
    answer = "ГОЛОС: 6\nСТРУКТУРА: 6\nПЕРСОНАЖИ: 6\nСЦЕНЫ: 6\nДИАЛОГ: 7\nИТОГ: 31\nСВЯЗНОСТЬ: ОК — нет"
    monkeypatch.setattr(pipeline_tasks, "_call", lambda *a, **k: answer)
    assert pipeline_tasks.score_text("Глава. " * 60, "", SOL)["verdict"] == "ПРИНЯТЬ"
    assert pipeline_tasks.score_text("Глава. " * 60, "", SONNET)["verdict"] == "НА ДОРАБОТКУ"   # порог 33


def test_continuity_checker_other_family(project_id, monkeypatch):
    from engine import plan_check
    from engine.continuity_checker import CONTINUITY_MODEL_KEY, continuity_checker_for
    _set(CONTINUITY_MODEL_KEY, "")
    assert continuity_checker_for(SONNET) == ""                 # проверка выключена — выключена
    _set(CONTINUITY_MODEL_KEY, SOL)
    assert continuity_checker_for(SONNET) == SOL
    # Набор сменили на «Пишет GPT» (проверяющий Sonnet), а круг — в старом запуске Sonnet
    _set(CONTINUITY_MODEL_KEY, SONNET)
    monkeypatch.setattr(plan_check, "plan_checker_model", lambda w: (SOL, "") if w == SONNET else ("", "нет"))
    assert continuity_checker_for(SONNET) == SOL
    monkeypatch.setattr(plan_check, "plan_checker_model", lambda w: ("", "нет"))
    assert continuity_checker_for(SONNET) == ""


def test_judge_gets_no_calibration_hint(project_id, monkeypatch):
    from engine import db_chapters
    from engine.db_narrative import create_pipeline_run
    from engine.pipeline_steps import step_judge
    monkeypatch.setattr(db_chapters, "get_judge_calibration_hint", lambda *a, **k: "ты завышаешь на +3.2")
    seen = {}

    def call(model, system, prompt, max_tokens=None, **kw):
        seen["system"] = system
        return "ГОЛОС: 7\nСТРУКТУРА: 7\nПЕРСОНАЖИ: 7\nСЦЕНЫ: 7\nДИАЛОГ: 7\nИТОГ: 35\nВЕРДИКТ: ПРИНЯТЬ"
    res = {"generated_text": "Глава. " * 50, "critique": "разбор"}
    step_judge(create_pipeline_run(project_id, 1, "w", "c", "w", SOL), 1, 1, SOL, call, res, project_id=project_id)
    assert "КАЛИБРОВКА" not in seen["system"] and "завышаешь" not in seen["system"]
