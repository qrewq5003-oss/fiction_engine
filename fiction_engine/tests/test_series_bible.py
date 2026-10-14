"""
Библия серии: места, вещи, время с историей; противоречие не перезаписывает.
"""
import json


def _e(name, attr, value, changed="", kind="место"):
    return {"kind": kind, "name": name, "attr": attr, "value": value, "changed": changed}


def test_record_history_and_conflict(project_id):
    from engine.series_bible import conflicts, current, history, record
    r = record(project_id, [_e("квартира Ларионовой", "этаж", "второй")], 3)
    assert len(r["added"]) == 1
    # То же значение — ничего
    assert record(project_id, [_e("Квартира Ларионовой", "Этаж", "второй")], 4) == \
        {"added": [], "changed": [], "conflicts": []}
    # Другое значение без события — противоречие, текущее не меняется
    r = record(project_id, [_e("квартира Ларионовой", "этаж", "третий")], 5)
    assert r["conflicts"][0]["was"] == "второй"
    assert [x["value"] for x in current(project_id)] == ["второй"]
    # Событие сюжета — законное изменение, прежняя запись в истории
    r = record(project_id, [_e("квартира Ларионовой", "этаж", "пятый", "переехала к сестре")], 7)
    assert r["changed"][0]["was"] == "второй"
    assert [x["value"] for x in current(project_id)] == ["пятый"]
    vals = [(h["chapter_num"], h["value"], h["status"]) for h in history(project_id, "квартира ларионовой", "этаж")]
    assert vals == [(3, "второй", "введено"), (5, "третий", "противоречие"), (7, "пятый", "изменено")]
    assert len(conflicts(project_id, 5)) == 1


def test_block_puts_focus_first_and_marks_change(project_id):
    from engine.series_bible import author_set, bible_block, record
    record(project_id, [_e("квартира Ларионовой", "этаж", "второй"),
                        _e("шарф Лаптева", "цвет", "красно-чёрный", kind="вещь")], 3)
    author_set(project_id, "вещь", "шарф Лаптева", "где", "у Веры", 6, "Вера изъяла его")
    b = bible_block(project_id, "Вера приходит к Лаптеву, на нём шарф")
    lines = b.splitlines()
    assert lines[0].startswith("БИБЛИЯ СЕРИИ") and "шарф Лаптева" in lines[1]
    assert "у Веры (с гл.6: Вера изъяла его)" in b and "квартира Ларионовой — этаж: второй" in b


def test_analysis_bible_goes_through_merge(project_id):
    from engine.db_state import merge_analysis_into_state
    from engine.series_bible import current
    raw = json.dumps({"bible": [_e("контора Гордеева", "этаж", "второй")]}, ensure_ascii=False)
    assert merge_analysis_into_state(project_id, raw, 3)["changed"]
    raw = json.dumps({"bible": [_e("контора Гордеева", "этаж", "пятый")]}, ensure_ascii=False)
    res = merge_analysis_into_state(project_id, raw, 4)
    assert res["bible_conflicts"] and any("Противоречие с библией" in f["field"] for f in res["fields"])
    assert [x["value"] for x in current(project_id)] == ["второй"]


def test_analysis_prompt_lists_known_entities(project_id):
    from engine.series_bible import known_for_analysis, record
    from engine.state import _build_analysis_prompt
    record(project_id, [_e("квартира Ларионовой", "этаж", "второй")], 3)
    p = _build_analysis_prompt(4, {"global_state": "", "plot_matrix": "", "memory_graph": ""},
                               "текст", None, known_for_analysis(project_id))
    assert "место: квартира Ларионовой: этаж — второй" in p and '"bible"' in p


def test_generator_and_continuity_get_bible(project_id):
    from unittest.mock import patch
    from engine.continuity_checker import _build_series_facts
    from engine.pipeline_context import build_context
    from engine.series_bible import record
    record(project_id, [_e("квартира Ларионовой", "этаж", "второй")], 3)
    with patch("engine.pipeline_context.build_consolidated_voice", return_value=""), \
         patch("engine.pipeline_context._build_exemplar_block", return_value=""), \
         patch("engine.pipeline_context._build_kb_block", return_value=""), \
         patch("engine.pipeline_context._build_engine_block", return_value=""), \
         patch("engine.pipeline_context.get_symbols_context", return_value=""), \
         patch("engine.pipeline_context.extract_relevant_state", return_value=""), \
         patch("engine.db.get_prep_context", return_value=""), \
         patch("engine.pipeline_context._maybe_save_debug_prompt", return_value=None):
        ctx = build_context(project_id, 4, "Задача главы")
    assert "БИБЛИЯ СЕРИИ" in ctx and "квартира Ларионовой — этаж: второй" in ctx
    assert "квартира Ларионовой" in _build_series_facts(project_id, 4)


def test_refinement_is_not_a_conflict(project_id):
    """Ложные противоречия замера 14.10 — уточнения, а не смена факта."""
    from engine.series_bible import current, history, record
    record(project_id, [_e("тайник", "где", "в полу, под ковром, в кабинете")], 4)
    r = record(project_id, [_e("тайник", "где", "в полу кабинета под ковром, крышка люка — половица")], 5)
    assert r["conflicts"] == []
    assert current(project_id)[0]["value"].startswith("в полу кабинета")
    assert [h["status"] for h in history(project_id, "тайник", "где")] == ["введено", "уточнено"]
    record(project_id, [_e("Кирпичный переулок", "дом", "15, квартира 8")], 4)
    assert record(project_id, [_e("Кирпичный переулок", "дом", "15")], 5)["conflicts"] == []
    # Числа и порядковые расходятся — противоречие
    record(project_id, [_e("контора", "этаж", "второй")], 3)
    assert record(project_id, [_e("контора", "этаж", "третий")], 4)["conflicts"]
