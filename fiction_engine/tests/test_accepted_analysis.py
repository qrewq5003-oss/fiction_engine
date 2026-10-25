"""Производное главы — по принятому тексту (разбор 21.10).

«Ночная смена» (20.10): анализ главы делался по черновику первого круга, правка
гл.1 убрала ошибку, а критик гл.3 упрекал главу «нерешённым разрывом из гл.1».
«Фон»: обещания, закрытые прежними версиями гл.20–21, остались закрытыми.
"""
import json

DRAFT = "Черновик главы. " * 40
FINAL = "Принятая глава после правки. " * 40
CRITIC = "claude_subscription::claude-haiku-5-5"


def _run(project_id, chapter=1):
    from engine.db_narrative import create_pipeline_run
    return create_pipeline_run(project_id, chapter, "w", CRITIC, "w", "j")


def _analysis(chapter=1, gap="ошибка черновика"):
    from engine.chapter_analyzer import ChapterAnalysis
    return ChapterAnalysis(project_id=1, chapter_num=chapter, analysis_quality="ok", logical_gaps=[gap])


# ─── Анализ главы ─────────────────────────────────────────────────────────────

def test_round_analysis_is_not_written_and_not_queued(project_id, monkeypatch):
    """Круг анализирует черновик для критика, но в chapter_analysis и в очередь State не пишет."""
    from engine import chapter_analyzer, state
    from engine.db import get_chapter_analysis, get_pending_updates
    from engine.pipeline_steps import step_chapter_analysis
    seen = {}

    def fake(pid, ch, text, call, persist=True):
        seen["persist"] = persist
        return _analysis()
    monkeypatch.setattr(chapter_analyzer, "analyze_chapter_deep", fake)
    monkeypatch.setattr(state, "queue_state_update_from_analysis",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("черновик в очередь State")))
    res = {}
    step_chapter_analysis(project_id, 1, DRAFT, CRITIC, lambda *a, **k: "", res)
    assert seen["persist"] is False and res["logical_gaps"] == ["ошибка черновика"]
    assert res["chapter_analysis_data"]["logical_gaps"] == ["ошибка черновика"]
    assert not get_chapter_analysis(project_id, 1) and not get_pending_updates(project_id)


def test_accepted_draft_takes_analysis_from_run(project_id, monkeypatch):
    """Принят проанализированный черновик — анализ из запуска, без вызова модели."""
    from engine import chapter_analyzer, pipeline
    from engine.db import get_chapter_analysis, save_pipeline_iteration
    from engine.plan_check import _text_hash
    monkeypatch.setattr(chapter_analyzer, "analyze_chapter_deep",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("лишний вызов")))
    run = _run(project_id)
    save_pipeline_iteration(run, 1, "generate", "w", "задача", DRAFT)
    save_pipeline_iteration(run, 1, pipeline.ANALYSIS_STAGE, CRITIC, _text_hash(DRAFT),
                            json.dumps(_analysis().to_dict(), ensure_ascii=False))
    assert pipeline.record_accepted_analysis(project_id, 1, DRAFT, run) is True
    assert get_chapter_analysis(project_id, 1)["logical_gaps"] == ["ошибка черновика"]


def test_accepted_edit_is_analysed_again(project_id, monkeypatch):
    """Принят круг правки — анализ заново, по принятому тексту, моделью критика запуска."""
    from engine import chapter_analyzer, pipeline
    from engine.db import save_pipeline_iteration
    from engine.plan_check import _text_hash
    seen = []

    class Done:
        analysis_quality = "ok"
    monkeypatch.setattr(chapter_analyzer, "analyze_chapter_deep",
                        lambda pid, ch, text, call, persist=True: seen.append(text) or Done())
    run = _run(project_id)
    save_pipeline_iteration(run, 1, "generate", "w", "задача", DRAFT)
    save_pipeline_iteration(run, 1, pipeline.ANALYSIS_STAGE, CRITIC, _text_hash(DRAFT), "{}")
    save_pipeline_iteration(run, 2, "edit", "w", "задача", FINAL)
    assert pipeline.record_accepted_analysis(project_id, 1, FINAL, run) is True and seen == [FINAL]
    # Без запуска (пересчёт после правки автора) — модель из вызова
    assert pipeline.record_accepted_analysis(project_id, 1, FINAL, 0, "w") is True and seen == [FINAL, FINAL]
    assert pipeline.record_accepted_analysis(project_id, 1, FINAL, 0, "") is False


# ─── Замена текста главы ──────────────────────────────────────────────────────

def test_forget_chapter_text(project_id):
    """Обещания, закрытые главой, — снова открыты; автозаметка уходит, план автора остаётся."""
    from engine.db import (get_chapter_analysis, get_director_note, get_l3_summaries,
                           save_chapter_analysis, save_director_note, save_l3_summary)
    from engine.db_chapters import forget_chapter_text
    save_l3_summary(project_id, 1, {"events": "гл.1", "promises": [
        {"id": "1_1", "text": "кто вынес пульт", "resolved": True, "resolved_chapter": 2}]})
    save_l3_summary(project_id, 2, {"events": "гл.2", "promises": []})
    save_chapter_analysis(project_id, 2, {"logical_gaps": ["старое"]})
    save_director_note(project_id, 2, "заметка модели по концу гл.2", source="auto")
    save_director_note(project_id, 1, "ПЛАН ГЛАВЫ 2 от автора")
    out = forget_chapter_text(project_id, 2)
    assert out["promises_reopened"] == 1 and out["auto_notes"] == 1
    l3 = {s["chapter_num"]: s for s in get_l3_summaries(project_id, 3, n=10)}
    assert 2 not in l3 and l3[1]["promises"][0]["resolved"] is False
    assert not get_chapter_analysis(project_id, 2)
    assert get_director_note(project_id, 3) is None and get_director_note(project_id, 2) == "ПЛАН ГЛАВЫ 2 от автора"


def test_prepare_replace_only_for_existing_chapter(project_id):
    from engine.db import save_chapter
    from engine.db_chapters import prepare_chapter_replace
    assert prepare_chapter_replace(project_id, 5) == {}
    save_chapter(project_id, 1, DRAFT, "Глава 1")
    out = prepare_chapter_replace(project_id, 1)
    assert "promises_reopened" in out and "state_restored" in out


def test_accept_over_existing_chapter_forgets_old_text(project_id, monkeypatch):
    """«Принять» поверх главы: сначала чистка производного прежнего текста, потом сохранение."""
    from engine import db_chapters
    from engine.db import save_chapter
    from web.app import app
    from web.blueprints import generate_pipeline
    from engine.db_settings import set_active_project
    set_active_project(project_id)
    save_chapter(project_id, 1, DRAFT, "Глава 1")
    order = []
    real = db_chapters.prepare_chapter_replace
    monkeypatch.setattr(db_chapters, "prepare_chapter_replace", lambda p, n: order.append(("forget", n)) or real(p, n))
    monkeypatch.setattr(generate_pipeline, "_start_state_update", lambda *a, **k: order.append("state") or "job")
    app.config.update(TESTING=True, FE_CSRF=False)
    run = _run(project_id)
    r = app.test_client().post("/pipeline/accept", json={"run_id": run, "chapter_num": 1, "final_text": FINAL,
                                                          "model_value": "w"})
    assert r.status_code == 200 and order == [("forget", 1), "state"]


# ─── «Разбор» правленого текста ───────────────────────────────────────────────

def test_review_keeps_author_text_as_round(project_id, monkeypatch):
    """Оценка «Разбора» — у текста с правками автора, а не у текста прошлого круга."""
    from engine import pipeline
    from engine.db import get_pipeline_iterations, save_pipeline_iteration
    monkeypatch.setattr(pipeline, "_call", lambda m, s, u, **k: "ГОЛОС: 7\nСТРУКТУРА: 7\nПЕРСОНАЖИ: 7\nСЦЕНЫ: 7\n"
                                                            "ДИАЛОГ: 7\nИТОГ: 35\nВЕРДИКТ: ПРИНЯТЬ")
    run = _run(project_id)
    save_pipeline_iteration(run, 1, "generate", "w", "задача", DRAFT)
    save_pipeline_iteration(run, 1, "judge", "j", DRAFT, "ИТОГ: 30", score=30, verdict="НА ДОРАБОТКУ")
    pipeline.continue_pipeline(run, project_id, 1, "задача", FINAL, "", steps=list(pipeline.REVIEW_ONLY))
    rounds = pipeline.pipeline_rounds(get_pipeline_iterations(run))
    assert [r["text"] for r in rounds] == [DRAFT, FINAL]


# ─── Дрейф голоса ─────────────────────────────────────────────────────────────

def test_drift_schedule_counts_chapters_before(project_id):
    """Переписанная гл.12 при проверенной гл.24 — тоже по расписанию от глав до неё."""
    from engine.db import save_drift_check
    from engine.db_narrative import should_run_drift_check
    save_drift_check(project_id, 9, 7.0)
    save_drift_check(project_id, 24, 7.0)
    assert should_run_drift_check(project_id, 12) is True
    assert should_run_drift_check(project_id, 10) is False


def test_round_drift_is_not_logged(project_id, monkeypatch):
    from engine import pipeline_drift
    from engine.db import get_last_drift_check
    from engine.pipeline_steps import step_drift_check
    monkeypatch.setattr(pipeline_drift, "should_check_drift", lambda *a: True)
    monkeypatch.setattr(pipeline_drift, "_get_reference", lambda *a, **k: ("эталон голоса", "профиль"), raising=False)
    monkeypatch.setattr(pipeline_drift, "drift_checker", lambda m, w: "chatgpt_subscription::gpt-6.1-sol@medium")
    res, calls = {}, []
    step_drift_check(project_id, 3, "Глава. " * 100, CRITIC,
                     lambda *a, **k: calls.append(1) or "ОЦЕНКА: 5\nПРОБЛЕМЫ: дрейф", res,
                     model_gen="claude_subscription::claude-sonnet-5-5")
    assert calls                                        # проверка была
    assert get_last_drift_check(project_id) is None     # но в журнал черновик не пишется


# ─── Ошибки прошлых глав, заглушка голоса ─────────────────────────────────────

def test_critic_and_continuity_get_no_past_gaps(project_id):
    from engine.continuity_checker import _build_series_facts
    from engine.db import save_chapter_analysis
    from engine.pipeline_steps import step_critique
    for ch in (1, 2):
        save_chapter_analysis(project_id, ch, {"logical_gaps": [f"разрыв из главы {ch}"],
                                               "opened_promises": [f"обещание главы {ch}"]})
    seen = {}

    def call(model, system, user, max_tokens=None, **kw):
        seen["continuity" if "JSON" in system else "critic"] = user
        return "[]" if "JSON" in system else "ГОЛОС: 7\nИТОГ: 35"
    res = {"generated_text": "Глава три. " * 60}
    step_critique(_run(project_id, 3), 1, 3, "c", call, res, project_id=project_id)
    assert "Глава три" in seen["critic"] and "разрыв из главы" not in seen["critic"]
    assert "разрыв из главы" not in seen.get("continuity", "")
    # Открытые обещания — из L3 (там отмечено закрытие), а не из opened_promises анализа
    from engine.db import save_l3_summary
    save_l3_summary(project_id, 1, {"events": "гл.1", "promises": [
        {"id": "1_0", "text": "Кто открыл подвал", "resolved": False},
        {"id": "1_1", "text": "Чей нож у двери", "resolved": True, "resolved_chapter": 2}]})
    facts = _build_series_facts(project_id, 3)
    assert "разрыв из главы" not in facts and "Кто открыл подвал" in facts and "Чей нож" not in facts


def test_voice_block_without_profile_and_chapters_is_empty():
    from engine.pipeline_context import build_consolidated_voice
    assert build_consolidated_voice(None, [], "quick") == ""


# ─── Правка главы автором ─────────────────────────────────────────────────────

def test_manual_edit_offers_recompute(project_id, monkeypatch):
    from engine.db import get_chapter, save_chapter
    from engine.db_settings import set_active_project
    from web.app import app
    from web.blueprints import generate_pipeline
    set_active_project(project_id)
    app.config.update(TESTING=True, FE_CSRF=False)
    save_chapter(project_id, 1, DRAFT, "Глава 1")
    c = app.test_client()
    assert c.post("/chapter/1/save", json={"text": FINAL}).get_json()["stale"] is True
    assert c.post("/chapter/1/save", json={"text": FINAL}).get_json()["stale"] is False
    seen = {}
    monkeypatch.setattr(generate_pipeline, "_start_state_update",
                        lambda p, n, m, t, run_id=0, state_stale=False: seen.update(n=n, t=t, m=m) or "job-1")
    monkeypatch.setattr("engine.pipeline_config.default_role_models", lambda: {"gen": "nano_gpt::x/y"})
    monkeypatch.setenv("NANO_GPT_API_KEY", "test-key")
    r = c.post("/chapter/1/recompute", json={}).get_json()
    assert r["state_job"] == "job-1" and seen["t"] == get_chapter(project_id, 1)["content"]
    assert seen["m"] == "nano_gpt::x/y"
    # Модель, выбранная автором, — вместо писателя набора
    c.post("/chapter/1/recompute", json={"model": "anthropic_direct::claude-opus-5-5@xhigh"})
    assert seen["m"] == "anthropic_direct::claude-opus-5-5@xhigh"
