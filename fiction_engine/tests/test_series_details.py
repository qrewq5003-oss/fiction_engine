"""
Детали серии в State: вещи, приметы мест, время, числа.

Замер 11.10: с памятью противоречий вдвое меньше, но остаются мелкие детали
(шуба с каракулевым воротником становится бобровой) — их не было в State.
"""
import json


def test_merge_dedupes_and_keeps_order():
    from engine.db_state import merge_series_details, series_details
    t = merge_series_details("## СЮЖЕТ\nлиния", ["шуба Ларионовой — каракулевый воротник"], 3)
    t = merge_series_details(t, ["Шуба Ларионовой — каракулевый воротник", "гараж — четвёртый в ряду"], 4)
    assert series_details(t) == ["гл.3: шуба Ларионовой — каракулевый воротник",
                                 "гл.4: гараж — четвёртый в ряду"]
    assert t.startswith("## СЮЖЕТ\nлиния") and t.count("## ДЕТАЛИ СЕРИИ") == 1


def test_merge_limits_length():
    from engine.db_state import SERIES_DETAILS_MAX, merge_series_details, series_details
    t = ""
    for i in range(SERIES_DETAILS_MAX + 10):
        t = merge_series_details(t, [f"деталь {i}"], i + 1)
    d = series_details(t)
    assert len(d) == SERIES_DETAILS_MAX and d[-1].endswith(f"деталь {SERIES_DETAILS_MAX + 9}")


def test_analysis_details_reach_state_and_generator(project_id):
    from engine.db import get_state, update_state
    from engine.db_state import merge_analysis_into_state
    from engine.pipeline_context import extract_relevant_state
    update_state(project_id, "## Вера\nСостояние: устала", "## ЛИНИИ\nдело Ларионовой", "")
    raw = json.dumps({"details": ["гараж — четвёртый в ряду", "ворота — подъёмные, новые"]})
    assert merge_analysis_into_state(project_id, raw, 3)["changed"]
    ctx = extract_relevant_state(get_state(project_id), "Глава 4. Вера едет к гаражу.")
    assert "ДЕТАЛИ СЕРИИ" in ctx and "гл.3: гараж — четвёртый в ряду" in ctx


def test_continuity_facts_include_details(project_id):
    from engine.continuity_checker import _build_series_facts
    from engine.db import update_state
    from engine.db_state import merge_series_details
    update_state(project_id, "## Вера\nСостояние: устала",
                 merge_series_details("", ["шуба — каракулевый воротник"], 3), "")
    assert "гл.3: шуба — каракулевый воротник" in _build_series_facts(project_id, 5)


def test_analysis_prompt_asks_for_details():
    from engine.state import _build_analysis_prompt
    p = _build_analysis_prompt(4, {"global_state": "", "plot_matrix": "", "memory_graph": ""}, "Текст.")
    assert '"details"' in p
