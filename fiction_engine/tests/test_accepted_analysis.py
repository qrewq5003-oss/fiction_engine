"""Анализ главы — по принятому тексту; ошибки прошлых глав не идут критику; голос без заглушки.

«Ночная смена» (20.10): анализ главы делался по черновику первого круга, правка
гл.1 убрала ошибку, а критик гл.3 упрекал главу «нерешённым разрывом из гл.1».
"""

DRAFT = "Черновик главы. " * 40
FINAL = "Принятая глава после правки. " * 40


def _run_with_rounds(project_id, *texts):
    from engine.db_narrative import create_pipeline_run, save_pipeline_iteration
    run = create_pipeline_run(project_id, 1, "w", "claude_subscription::claude-haiku-5-5", "w", "j")
    for i, t in enumerate(texts, 1):
        save_pipeline_iteration(run, i, "generate" if i == 1 else "edit", "w", "задача", t)
        save_pipeline_iteration(run, i, "judge", "j", t, "ИТОГ: 33", score=33, verdict="ПРИНЯТЬ")
    return run


def test_reanalyze_when_accepted_round_is_not_draft(project_id, monkeypatch):
    from engine import chapter_analyzer, pipeline
    seen = []

    class Done:
        analysis_quality = "full"

    def fake(pid, ch, text, call):
        seen.append(text)
        return Done()
    monkeypatch.setattr(chapter_analyzer, "analyze_chapter_deep", fake)
    run = _run_with_rounds(project_id, DRAFT, FINAL)
    assert pipeline.reanalyze_accepted(project_id, 1, run, FINAL) is True
    assert seen == [FINAL]
    # Принят сам черновик — его анализ уже есть, второй вызов не нужен
    assert pipeline.reanalyze_accepted(project_id, 1, run, DRAFT) is False
    assert seen == [FINAL]


def test_critic_and_continuity_get_no_past_gaps(project_id):
    from engine.continuity_checker import _build_series_facts
    from engine.db import save_chapter_analysis
    from engine.pipeline_steps import step_critique
    from engine.db_narrative import create_pipeline_run
    for ch in (1, 2):
        save_chapter_analysis(project_id, ch, {"logical_gaps": [f"разрыв из главы {ch}"],
                                               "opened_promises": [f"обещание главы {ch}"]})
    seen = {}

    def call(model, system, user, max_tokens=None, **kw):
        seen["continuity" if "JSON" in system else "critic"] = user
        return "[]" if "JSON" in system else "ГОЛОС: 7\nИТОГ: 35"
    res = {"generated_text": "Глава три. " * 60}
    step_critique(create_pipeline_run(project_id, 3, "w", "c", "w", "j"), 1, 3, "c", call, res,
                  project_id=project_id)
    assert "Глава три" in seen["critic"] and "разрыв из главы" not in seen["critic"]
    assert "разрыв из главы" not in seen.get("continuity", "")
    facts = _build_series_facts(project_id, 3)
    assert "разрыв из главы" not in facts and "обещание главы 1" in facts


def test_voice_block_without_profile_and_chapters_is_empty():
    from engine.pipeline_context import build_consolidated_voice
    assert build_consolidated_voice(None, [], "quick") == ""
