"""Тихие сбои (разбор 21.10, группа 3): сбой не выдаётся за успех."""
import pytest


def _client(project_id):
    from engine.db_settings import set_active_project
    from web.app import app
    set_active_project(project_id)
    app.config.update(TESTING=True, FE_CSRF=False)
    return app.test_client()


def test_unparsed_analysis_does_not_replace_previous(project_id):
    """Неразобранный ответ анализа не затирает прежний анализ главы и не считается успехом."""
    from engine.chapter_analyzer import analyze_chapter_deep
    from engine.db import get_chapter_analysis, save_chapter
    from engine.pipeline import record_accepted_analysis
    text = "Глава один. " * 40
    save_chapter(project_id, 1, text, "Глава 1")
    good = '{"logical_gaps": ["прежний разрыв"], "closing_type": "action"}'
    assert analyze_chapter_deep(project_id, 1, text, lambda p: good).analysis_quality == "ok"
    bad = analyze_chapter_deep(project_id, 1, text, lambda p: "модель ответила прозой")
    assert bad.analysis_quality == "partial"
    assert get_chapter_analysis(project_id, 1)["logical_gaps"] == ["прежний разрыв"]
    from unittest.mock import patch
    with patch("engine.pipeline._call", return_value="опять проза"):
        assert record_accepted_analysis(project_id, 1, text, 0, "m::x") is False


def test_continuity_failure_is_not_clean(project_id):
    from engine.continuity_checker import check_continuity, check_continuity_or_raise
    from unittest.mock import patch
    with patch("engine.continuity_checker._has_enough_data", return_value=True), \
         patch("engine.continuity_checker._build_series_facts", return_value="Вера — следователь"):
        with pytest.raises(ValueError):
            check_continuity_or_raise(project_id, 5, "Глава. " * 50, lambda p: "не json")
        assert check_continuity(project_id, 5, "Глава. " * 50, lambda p: "не json") == []   # конвейер — как было
        ok = '{"violations": [{"fact": "Вера — следователь", "violation": "Вера — врач"}]}'
        assert len(check_continuity_or_raise(project_id, 5, "Глава. " * 50, lambda p: ok)) == 1


def test_state_apply_keeps_analysis_when_merge_breaks(project_id):
    from unittest.mock import patch
    from engine.db import get_pending_updates
    from engine.db_state import save_state_update
    uid = save_state_update(project_id, 1, '{"global_state_changes": []}')
    with patch("engine.db.merge_analysis_into_state", side_effect=RuntimeError("сломалось")):
        r = _client(project_id).post(f"/state/apply/{uid}", json={})
    assert r.status_code == 500 and "в очереди" in r.get_json()["error"]
    assert any(u["id"] == uid for u in get_pending_updates(project_id))


def test_after_saved_names_failed_steps(project_id, monkeypatch):
    from web.blueprints.helpers import after_chapter_saved

    def boom(*a, **k):
        raise RuntimeError("L3 упал")
    monkeypatch.setattr("engine.pipeline.generate_l3", boom)
    monkeypatch.setattr("engine.pipeline.auto_drift_check_if_needed", lambda *a, **k: None)
    monkeypatch.setattr("engine.pipeline.generate_director_note_for_chapter", lambda *a, **k: None)
    steps = []
    out = after_chapter_saved(project_id, 1, "Глава. " * 50, "", step=steps.append)
    assert out["failed"] == ["память L3"] and steps[:2] == ["память L3", "дрейф голоса"]
