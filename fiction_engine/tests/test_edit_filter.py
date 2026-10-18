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
    assert rep == {"checked": 2, "kept": 1, "reverted": 1}
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
    assert results["edit_report"]["filter"] == {"checked": 1, "kept": 0, "reverted": 1}
    assert results["edit_report"]["changed"] == 0
