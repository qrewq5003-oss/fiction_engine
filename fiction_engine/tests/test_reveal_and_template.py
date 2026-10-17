"""
Книга-прогон 17.10 (12 глав): правщик непрерывности переписал признание
убийцы в отрицание; шаблонный «### [Имя]» уходил писателю все 12 глав;
единственный конфликт библии был ложным — два описания одной калитки.
"""
import json


# ─── Разоблачение — не противоречие ───────────────────────────────────────────

def test_checker_prompt_is_the_measured_one():
    """Проверяющему — без плана и правила о разоблачениях: с ними Sol находил 56 из 98 вместо 91–98."""
    from engine.continuity_checker import check_against_chapters
    seen = []
    check_against_chapters(2, "текст", [{"number": 1, "content": "прошлое"}],
                           lambda p: (seen.append(p), "[]")[1])
    assert "ПЛАН ЭТОЙ ГЛАВЫ" not in seen[0] and "РАЗОБЛАЧЕНИЕ" not in seen[0]


def test_fixer_without_plan_has_no_plan_block():
    from engine.continuity_fix import fix_contradictions
    seen = []
    fix_contradictions(2, "текст главы", [{"chapter_a": 1, "quote_a": "a", "quote_b": "b", "what": "w"}],
                       [{"number": 1, "content": "прошлое"}], lambda p: (seen.append(p), '{"edits": []}')[1])
    assert "ПЛАН ЭТОЙ ГЛАВЫ" not in seen[0]


def test_fixer_is_told_not_to_undo_confessions():
    from engine.continuity_fix import fix_contradictions
    seen = []
    fix_contradictions(12, "Я была на маяке.", [{"chapter_a": 10, "quote_a": "не была на маяке",
                                                  "quote_b": "Я была на маяке", "what": "алиби"}],
                       [{"number": 10, "content": "Я не была на маяке."}],
                       lambda p: (seen.append(p), '{"edits": []}')[1], plan="Кравец признаётся")
    assert "Признания, разоблачения и раскрытие тайн не трогай" in seen[0] and "Кравец признаётся" in seen[0]


def test_cross_check_passes_the_chapter_plan_to_the_fixer(project_id, monkeypatch):
    from engine.db import save_chapter, save_director_note, set_setting
    import engine.continuity_checker as cc
    import engine.continuity_fix as cf
    save_chapter(project_id, 1, "Я не была на маяке, сказала Кравец.", "1")
    save_director_note(project_id, 1, "ПЛАН ГЛАВЫ 2\nСЦЕНА 1: Кравец признаётся")
    set_setting("continuity_model", "nano_gpt::x")
    set_setting("continuity_fix_model", "nano_gpt::y")
    finding = {"chapter_a": 1, "quote_a": "не была на маяке", "quote_b": "была на маяке", "what": "алиби"}
    monkeypatch.setattr(cc, "check_against_chapters", lambda n, t, prev, call: [finding])
    got = {}

    def fake_fix(n, text, found, prev, call, plan=""):
        got["plan"] = plan
        return {"text": text, "edits": [], "applied": [], "failed": []}
    monkeypatch.setattr(cf, "fix_contradictions", fake_fix)
    cc.cross_check_and_fix(project_id, 2, "Я была на маяке.", "m::m", lambda *a, **k: "")
    assert "Кравец признаётся" in got["plan"]


# ─── Шаблонный персонаж ───────────────────────────────────────────────────────

def test_template_character_dropped_on_merge(project_id):
    from engine.db_core import _default_global
    from engine.db_state import get_state, merge_analysis_into_state, update_state
    update_state(project_id, global_state=_default_global())
    merge_analysis_into_state(project_id, json.dumps({
        "global_state_changes": [{"name": "Анна Леонова", "состояние": "приехала на остров"}],
        "plot_changes": {}, "memory_changes": []}, ensure_ascii=False), 1)
    g = get_state(project_id)["global_state"]
    assert "### Анна Леонова" in g and "[Имя]" not in g
    assert "## МИР" in g                              # остальной шаблон на месте


def test_filled_bracket_character_is_kept():
    from engine.state_merge import drop_template_characters
    t = "## ПЕРСОНАЖИ\n\n### [Незнакомец]\nСОСТОЯНИЕ: следит из «пассата»\nЛОКАЦИЯ: []\n\n---\n"
    assert "[Незнакомец]" in drop_template_characters(t)


# ─── Библия: описания, которые дополняют друг друга ───────────────────────────

def test_complementary_descriptions_are_not_a_conflict(project_id):
    from engine.series_bible import conflicts, current, record
    record(project_id, [{"kind": "место", "name": "дом Громова", "attr": "калитка",
                         "value": "держится на одной петле, задевает землю"}], 2)
    res = record(project_id, [{"kind": "место", "name": "дом Громова", "attr": "калитка",
                               "value": "скоба недавно отогнута, свежий загиб, блестящий на изломе"}], 4)
    assert res["conflicts"] == [] and conflicts(project_id) == []
    val = next(f["value"] for f in current(project_id) if f["attr"] == "калитка")
    assert "одной петле" in val and "скоба" in val


def test_real_conflicts_stay():
    from engine.series_bible import complements
    assert not complements("третий этаж", "пятый этаж")
    assert not complements("белая башня, 84 ступени до галереи", "кирпичная башня, 60 ступеней до галереи")
    assert not complements("красный шарф с длинной бахромой и кистями", "синий шарф с длинной бахромой и кистями")
    assert complements("держится на одной петле, задевает землю",
                       "скоба недавно отогнута, свежий загиб, блестящий на изломе")
