"""Неверное задание модели (разбор 21.10, группа 2)."""
import json


def _chapters(project_id, n):
    from engine.db import save_chapter
    for i in range(1, n + 1):
        save_chapter(project_id, i, f"Глава {i}. " * 40, f"Глава {i}")


def test_old_book_without_snapshot_gets_no_now_fields(project_id):
    """Старая книга без снимков: конец книги не уходит работе над главой из середины."""
    from engine.db_state import state_for_chapter, update_state
    _chapters(project_id, 3)
    update_state(project_id,
                 global_state="## ПЕРСОНАЖИ\n### Вера\nРОЛЬ: следователь\nЗНАЕТ: убийца — Марат\n"
                              "СОСТОЯНИЕ: обвинила Марата\n",
                 plot_matrix="## ЛИНИИ\nдело\n\n## ДЕТАЛИ СЕРИИ\n- гл.1: синяя дверь\n- гл.3: Марат в наручниках",
                 memory_graph="Вера → знает → Марат убийца")
    st = state_for_chapter(project_id, 2)
    assert "следователь" in st["global_state"] and "Марат" not in st["global_state"]
    assert "синяя дверь" in st["plot_matrix"] and "наручниках" not in st["plot_matrix"]
    assert st["memory_graph"] == ""
    assert "Марат" in state_for_chapter(project_id, 4)["global_state"]     # новая глава — нынешний


def test_old_prompt_builder_uses_previous_chapter_context(project_id):
    """Старый сборщик: «где закончилась прошлая глава» — из применённого анализа гл.N−1 (JSON)."""
    from engine.db import get_project
    from engine.db_state import mark_update_applied, save_state_update
    from engine.state_prompts import build_prompt
    _chapters(project_id, 2)
    u1 = save_state_update(project_id, 1, json.dumps({"next_context": "Вера у двери морга"}, ensure_ascii=False))
    mark_update_applied(project_id, u1)
    save_state_update(project_id, 2, json.dumps({"next_context": "ЧЕРНОВИК ГЛАВЫ 2"}, ensure_ascii=False))
    prompt = build_prompt(project_id, 2, "quality", get_project(project_id))
    assert "Вера у двери морга" in prompt and "ЧЕРНОВИК" not in prompt


def test_promises_open_at_chapter():
    from engine.l3_memory import get_active_promises
    ps = [{"id": "a", "resolved": True, "resolved_chapter": 14}, {"id": "b", "resolved": False},
          {"id": "c", "resolved": True, "resolved_chapter": 5}]
    assert [p["id"] for p in get_active_promises(ps)] == ["b"]
    assert [p["id"] for p in get_active_promises(ps, 12)] == ["a", "b"]


def test_bible_rewritten_early_chapter_does_not_win_end_of_book(project_id):
    from engine.series_bible import current, record
    fact = {"kind": "персонаж", "name": "Вера", "attr": "звание", "changed": ""}
    record(project_id, [dict(fact, value="лейтенант")], 1)
    record(project_id, [dict(fact, value="капитан", changed="повышена")], 20)
    record(project_id, [dict(fact, value="лейтенант")], 12)          # пересчёт гл.12
    assert current(project_id)[0]["value"] == "капитан"
    assert current(project_id, 13)[0]["value"] == "лейтенант"


def test_relevant_state_keeps_early_details_of_this_chapter():
    from engine.pipeline_context import DETAILS_RECENT, extract_relevant_state
    details = ["гл.1: подсобка театра заперта на висячий замок"] + [f"гл.{i}: мелочь {i}" for i in range(2, 60)]
    plot = "## ДЕТАЛИ СЕРИИ\n" + "\n".join(f"- {d}" for d in details)
    out = extract_relevant_state({"global_state": "", "plot_matrix": plot, "memory_graph": ""},
                                 "Сцена: Вера вскрывает подсобку", before_chapter=61)
    assert "висячий замок" in out and "мелочь 59" in out
    assert "мелочь 20" not in out and out.count("\n- ") == DETAILS_RECENT + 1


def test_point_editor_self_mode_not_contradicted():
    from engine.point_edit import SELF_REVIEW, SYS_POINT_EDITOR
    assert "найди" in SELF_REVIEW and "найти их самому" in SYS_POINT_EDITOR
