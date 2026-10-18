"""Фильтр правок судьёй (engine/edit_filter): отвергнутые судьёй места откатываются."""
import json
import re

OLD = "Первый абзац.\n\nВторой абзац.\n\nТретий абзац.\n\nЧетвёртый."
NEW = "Первый абзац, лучше.\n\nВторой абзац.\n\nТретий абзац, хуже.\n\nЧетвёртый."
SOL = "chatgpt_subscription::gpt-6.1-sol@medium"
SONNET = "claude_subscription::claude-sonnet-5-5"


def _judge(prefer):
    """Судья: по каждому фрагменту выбирает вариант с подстрокой prefer[i] (или «равно»)."""
    seen = []

    def call(model, system, prompt):
        seen.append(model)
        choices = []
        for n, (v1, v2) in enumerate(re.findall(r"--- Вариант 1 ---\n(.*?)\n--- Вариант 2 ---\n(.*?)(?=\n\n=== |\Z)",
                                                prompt, re.S), 1):
            want = prefer[n - 1]
            choices.append({"n": n, "better": "равно" if want == "=" else "1" if want in v1 else "2"})
        return json.dumps({"choices": choices}, ensure_ascii=False)
    call.seen = seen
    return call


def test_keeps_chosen_reverts_rejected():
    from engine.edit_filter import filter_edits
    call = _judge(["лучше", "Третий абзац."])            # 1-я правка — да, 2-я — исходник
    text, rep = filter_edits(OLD, NEW, SONNET, SOL, call, seed=1)
    assert text == "Первый абзац, лучше.\n\nВторой абзац.\n\nТретий абзац.\n\nЧетвёртый."
    assert rep == {"checked": 2, "kept": 1, "reverted": 1, "plan_kept": 0}
    assert call.seen == [SONNET]


def test_equal_is_reverted():
    from engine.edit_filter import filter_edits
    text, rep = filter_edits(OLD, NEW, SONNET, SOL, _judge(["=", "хуже"]), seed=2)
    assert text.startswith("Первый абзац.\n\n") and "хуже" in text and rep["reverted"] == 1


def test_same_family_and_garbage_keep_edits():
    from engine.edit_filter import filter_edits
    text, rep = filter_edits(OLD, NEW, SOL, SOL, _judge(["Первый абзац.", "Третий абзац."]))
    assert text == NEW and "той же семьи" in rep["skipped"]
    text, rep = filter_edits(OLD, NEW, SONNET, SOL, lambda m, s, p: "не знаю")
    assert text == NEW and "не разобран" in rep["skipped"]
    assert filter_edits(OLD, OLD, SONNET, SOL, lambda m, s, p: 1 / 0)[1]["checked"] == 0


def test_insertion_reverted_cleanly():
    from engine.edit_filter import filter_edits
    new = "Первый абзац.\n\nВставка редактора.\n\nВторой абзац.\n\nТретий абзац.\n\nЧетвёртый."
    text, rep = filter_edits(OLD, new, SONNET, SOL, _judge(["(абзаца нет)"]), seed=3)
    assert text == OLD and rep["reverted"] == 1


def test_step_edit_filters_with_judge(project_id):
    from unittest.mock import patch
    from engine.pipeline_steps import step_edit
    old = "Лампа не горела.\n\nСерёгин ждал у двери."
    results = {}

    def call(model, system, prompt):
        if model == SONNET:                                   # судья: «исходник» по всем местам
            n = prompt.count("=== ФРАГМЕНТ")
            return json.dumps({"choices": [{"n": i, "better": "1" if "Лампа не горела." in prompt.split(
                "--- Вариант 1 ---\n")[i].split("\n--- Вариант 2")[0] else "2"} for i in range(1, n + 1)]})
        return json.dumps({"edits": [{"old": "Лампа не горела.", "new": "Лампа была погашена."}]},
                          ensure_ascii=False)

    with patch("engine.pipeline_steps.save_pipeline_iteration"):
        step_edit(1, 2, "Глава 1", old, "разбор", SOL, call, results, model_judge=SONNET)
    assert results["generated_text"] == old
    assert results["edit_report"]["filter"] == {"checked": 1, "kept": 0, "reverted": 1, "plan_kept": 0}
    assert results["edit_report"]["changed"] == 0


def test_plan_edits_are_not_filtered():
    """Правки по плану (PLAN_MARK) судье не показываются и не откатываются."""
    from engine.edit_filter import filter_edits
    from engine.point_edit import plan_edit_texts
    keep = plan_edit_texts([{"new": "Первый абзац, лучше.", "why": "ПЛАН: сцена днём"},
                            {"new": "Третий абзац, хуже.", "why": "ритм"}])
    assert keep == ["Первый абзац, лучше."]
    call = _judge(["Третий абзац."])                     # судья видит только одно место
    text, rep = filter_edits(OLD, NEW, SONNET, SOL, call, seed=4, keep=keep)
    assert text == "Первый абзац, лучше.\n\nВторой абзац.\n\nТретий абзац.\n\nЧетвёртый."
    assert rep == {"checked": 1, "kept": 0, "reverted": 1, "plan_kept": 1}


def test_step_edit_gives_plan_misses_to_editor(project_id):
    """Пункты плана «нет»/«частично» — первыми в задании редактору; правка по плану переживает фильтр."""
    from unittest.mock import patch
    from engine.db import save_director_note
    from engine.pipeline_steps import step_edit
    save_director_note(project_id, 0, "СЦЕНА 1: Пристань\n  Когда: пятница, утро\n\nСЦЕНА 2: Каюта")
    from engine.db import set_setting
    set_setting("continuity_model", SONNET)          # проверяющий плана — не семья редактора
    old = "Лампа не горела.\n\nСерёгин ждал у двери."
    prompts, results = [], {}

    def call(model, system, prompt):
        prompts.append((model, prompt))
        if "план главы" in prompt.lower() and "=== ПЛАН ===" in prompt:      # сверка
            return json.dumps({"items": [{"n": 1, "status": "нет", "quote": "", "note": "не названа пятница"},
                                         {"n": 2, "status": "есть", "quote": "Серёгин ждал у двери", "note": ""}]},
                              ensure_ascii=False)
        if "=== ФРАГМЕНТ" in prompt:                                       # фильтр: всё — исходник
            return json.dumps({"choices": [{"n": 1, "better": "1"}]})
        return json.dumps({"edits": [{"old": "Лампа не горела.", "new": "В пятницу утром лампа не горела.",
                                      "why": "ПЛАН: пятница, утро"}]}, ensure_ascii=False)

    with patch("engine.pipeline_steps.save_pipeline_iteration"):
        step_edit(1, 2, "Глава 1", old, "разбор", SOL, call, results, model_judge=SONNET,
                  project_id=project_id, chapter_num=1)
    editor = [p for m, p in prompts if "ПЛАН ГЛАВЫ" in p]
    assert editor and "не названа пятница" in editor[0]
    assert results["generated_text"].startswith("В пятницу утром лампа не горела.")
    assert results["edit_report"]["plan_missing"] == 1 and results["edit_report"]["filter"]["plan_kept"] == 1
    assert "plan_error" not in results["edit_report"]


def test_step_edit_plan_check_failure_is_reported(project_id):
    """Сбой сверки — один повтор, затем ошибка в отчёте, а не молчаливые «0 пунктов» (книга 18.10)."""
    from unittest.mock import patch
    from engine.db import save_director_note, set_setting
    from engine.pipeline_steps import step_edit
    save_director_note(project_id, 0, "СЦЕНА 1: Пристань\n  Когда: пятница, утро")
    set_setting("continuity_model", SONNET)
    checks, results = [], {}

    def call(model, system, prompt):
        if "=== ПЛАН ===" in prompt:
            checks.append(1)
            raise RuntimeError("codex: usage limit")
        return json.dumps({"edits": []})

    with patch("engine.pipeline_steps.save_pipeline_iteration"):
        step_edit(1, 2, "Глава 1", "Лампа не горела.", "разбор", SOL, call, results, model_judge=SONNET,
                  project_id=project_id, chapter_num=1)
    assert len(checks) == 2
    assert results["edit_report"]["plan_missing"] == 0 and "usage limit" in results["edit_report"]["plan_error"]
    assert results["generated_text"] == "Лампа не горела."
