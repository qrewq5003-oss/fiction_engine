"""Переписывание главы из середины книги (разбор 21.10, пакет 4).

State — конец книги. Писатель переписываемой гл.12 «Фона» получил бы «Марат
обвинён» и всю разгадку в «ЗНАЕТ» героини; анализ переписанной главы
откатывал «ГДЕ_СЕЙЧАС» к ней и ломал «Откатить» последней главы.
"""
import json

TEXT = "Глава. " * 40


def _book(project_id, n):
    from engine.db import save_chapter
    for k in range(1, n + 1):
        save_chapter(project_id, k, f"Глава {k}. " + TEXT, f"Глава {k}")


def _state(project_id, where, reason):
    from engine.db_state import update_state
    update_state(project_id, plot_matrix=f"## ОСНОВНАЯ ЛИНИЯ\nГДЕ_СЕЙЧАС: {where}\n", _snapshot_reason=reason)


def test_writer_of_rewritten_chapter_sees_state_before_it(project_id):
    from engine.db_state import SNAPSHOT_BEFORE, state_for_chapter
    _state(project_id, "после гл.1", "")
    _state(project_id, "после гл.2", f"{SNAPSHOT_BEFORE}2")     # снимок — State до анализа гл.2
    _state(project_id, "после гл.3", f"{SNAPSHOT_BEFORE}3")
    _book(project_id, 3)
    assert "после гл.1" in state_for_chapter(project_id, 2)["plot_matrix"]
    assert "после гл.3" in state_for_chapter(project_id, 4)["plot_matrix"]   # новая глава — нынешний


def test_chapter_snapshots_are_not_evicted(project_id):
    from engine.db_state import SNAPSHOT_BEFORE, get_state_history, snapshot_state
    snapshot_state(project_id, reason=f"{SNAPSHOT_BEFORE}1")
    for k in range(30):
        snapshot_state(project_id, reason=f"авто {k}")
    reasons = [h["reason"] for h in get_state_history(project_id)]
    assert f"{SNAPSHOT_BEFORE}1" in reasons and len([r for r in reasons if r.startswith("авто")]) == 20


def test_middle_chapter_merge_keeps_now_and_rollback(project_id):
    """Анализ переписанной главы из середины: её детали — да, «сейчас» — нет; откат последней цел."""
    from engine.db_chapters import rollback_info
    from engine.db_state import SNAPSHOT_BEFORE, SNAPSHOT_RECOMPUTE, get_state, get_state_history
    from engine.state_merge import merge_analysis_into_state
    _state(project_id, "конец книги", "")
    _state(project_id, "конец книги", f"{SNAPSHOT_BEFORE}3")
    _book(project_id, 3)
    raw = json.dumps({"plot_changes": {"где_сейчас": "в подсобке, гл.2"},
                      "details": ["ключ от подсобки висит у вахты"]}, ensure_ascii=False)
    res = merge_analysis_into_state(project_id, raw, 2)
    plot = get_state(project_id)["plot_matrix"]
    assert res["changed"] and "гл.2: ключ от подсобки" in plot and "в подсобке" not in plot
    assert get_state_history(project_id)[0]["reason"] == f"{SNAPSHOT_RECOMPUTE}2"
    assert rollback_info(project_id, 3)["snapshot"]["reason"] == f"{SNAPSHOT_BEFORE}3"


def test_last_chapter_merge_moves_now(project_id):
    from engine.db_state import get_state
    from engine.state_merge import merge_analysis_into_state
    _state(project_id, "после гл.2", "")
    _book(project_id, 3)
    merge_analysis_into_state(project_id, json.dumps({"plot_changes": {"где_сейчас": "у гаражей"}},
                                                     ensure_ascii=False), 3)
    assert "у гаражей" in get_state(project_id)["plot_matrix"]
