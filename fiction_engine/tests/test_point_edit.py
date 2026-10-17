"""Точечная редактура (engine/point_edit): правки и вставки вместо переписывания главы."""
import json

TEXT = ("Анна поднялась на галерею. Ветер бил в стекло фонаря.\n\n"
        "Она посмотрела вниз, на будку смотрителя. Лампа не горела.\n\n"
        "Серёгин ждал внизу и курил, пряча сигарету в кулак.")


def _call(edits):
    seen = []

    def call(prompt):
        seen.append(prompt)
        return json.dumps({"edits": edits}, ensure_ascii=False)
    return call, seen


def test_replace_and_insert_leave_the_rest_word_for_word():
    from engine.point_edit import point_edit
    call, seen = _call([
        {"old": "Ветер бил в стекло фонаря.", "new": "Ветер с озера бил в стекло фонаря, и рама гудела.",
         "why": "мало деталей"},
        {"after": "Лампа не горела.", "new": "Громов не гасил её ни разу за тридцать лет.",
         "why": "критик: не объяснено, почему это важно"}])
    rep = point_edit(TEXT, "Мало деталей; не ясно, почему лампа важна.", "Глава 6. Маяк заново.", call)
    out = rep["text"]
    assert "и рама гудела" in out and "ни разу за тридцать лет" in out
    assert out.index("Лампа не горела.") < out.index("Громов не гасил") < out.index("Серёгин ждал")
    assert "Серёгин ждал внизу и курил, пряча сигарету в кулак." in out      # не тронуто
    assert len(rep["applied"]) == 2 and rep["failed"] == [] and 0 < rep["changed"] < 0.5
    assert "Глава 6. Маяк заново." in seen[0] and "почему лампа важна" in seen[0]


def test_fragment_with_other_quotes_and_dashes_is_found():
    from engine.point_edit import point_edit
    call, _ = _call([{"old": "Она посмотрела вниз на будку смотрителя", "new": "Она глянула вниз, на будку"}])
    rep = point_edit(TEXT, "к", "з", call)
    assert "Она глянула вниз, на будку" in rep["text"] and rep["applied"][0]["way"] == "words"


def test_missing_fragment_and_bad_answer_keep_text():
    from engine.point_edit import point_edit
    call, _ = _call([{"old": "Кравец стояла у перил.", "new": "x"},
                     {"after": "Этого предложения нет.", "new": "вставка"}])
    rep = point_edit(TEXT, "к", "з", call)
    assert rep["text"] == TEXT and rep["changed"] == 0
    assert [f["why"] for f in rep["failed"]] == ["не найдено в главе", "место вставки не найдено в главе"]
    rep = point_edit(TEXT, "к", "з", lambda p: "Вот переписанная глава целиком: …")
    assert rep["text"] == TEXT and "не разобран" in rep["failed"][0]["why"]


def test_mode_setting(project_id):
    from engine.db import set_setting
    from engine.point_edit import edit_mode
    assert edit_mode() == "points"
    set_setting("edit_mode", "rewrite")
    assert edit_mode() == "rewrite"
    set_setting("edit_mode", "чепуха")
    assert edit_mode() == "points"


def test_step_edit_points_mode(project_id):
    from unittest.mock import patch
    from engine.pipeline_steps import step_edit
    prompts, results = [], {}

    def call(model, system, prompt):
        prompts.append((system, prompt))
        return json.dumps({"edits": [{"old": "Лампа не горела.", "new": "Лампа была погашена."}]},
                          ensure_ascii=False)

    with patch("engine.pipeline_steps.save_pipeline_iteration") as saved:
        step_edit(1, 2, "Глава 1. ПРАВКА: допиши сцену с Митяем", TEXT, "лампа — штамп", "m::m", call, results)
    assert "Лампа была погашена." in results["generated_text"] and "Серёгин ждал" in results["generated_text"]
    assert results["edit_report"]["mode"] == "points" and results["edit_report"]["applied"] == 1
    assert "ПРАВКА: допиши сцену с Митяем" in prompts[0][1]          # задача автора видна редактору
    assert saved.call_args[0][2] == "edit"


def test_rewrite_mode_also_sees_the_task(project_id):
    from unittest.mock import patch
    from engine.db import set_setting
    from engine.pipeline_steps import step_edit
    set_setting("edit_mode", "rewrite")
    prompts, results = [], {}
    with patch("engine.pipeline_steps.save_pipeline_iteration"):
        step_edit(1, 2, "ПРАВКА: допиши сцену", TEXT, "критика", "m::m",
                  lambda m, s, p: (prompts.append(p), "Новый текст главы. " * 20)[1], results)
    assert "ПРАВКА: допиши сцену" in prompts[0] and results["edit_report"]["mode"] == "rewrite"
    assert results["edit_report"]["changed"] > 0.9
