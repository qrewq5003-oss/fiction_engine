"""
Сверка новой главы с полным текстом прошлых: противоречия парой цитат,
цитаты проверяются по тексту.
"""
import json

import pytest

CH3 = ("Квартира вдовы была на втором этаже, окна во двор. Лаптев снял красно-чёрный "
       "клетчатый шарф и повесил его на крючок у двери.")
CH4 = ("Вера поднялась на третий этаж к квартире вдовы и позвонила. Лаптев вошёл в "
       "зелёно-сером шарфе, будто другого у него и не было.")


def _answer(items):
    return lambda prompt: json.dumps({"contradictions": items}, ensure_ascii=False)


def test_quote_in_ignores_punctuation_and_case():
    from engine.continuity_checker import quote_in
    assert quote_in("квартира вдовы была на втором этаже", CH3)
    assert quote_in("Квартира вдовы… повесил его на крючок", CH3)
    assert not quote_in("квартира вдовы была на пятом этаже", CH3)
    assert not quote_in("на втором", CH3)       # меньше трёх слов — не цитата


def test_keeps_only_pairs_found_in_text():
    from engine.continuity_checker import check_against_chapters
    items = [
        {"chapter_a": 3, "quote_a": "Квартира вдовы была на втором этаже",
         "quote_b": "Вера поднялась на третий этаж к квартире вдовы", "what": "этаж квартиры"},
        # Цитаты нет в новой главе — выдумано
        {"chapter_a": 3, "quote_a": "снял красно-чёрный клетчатый шарф",
         "quote_b": "Лаптев пришёл в синем пальто", "what": "одежда"},
        # Глава, которой не показывали
        {"chapter_a": 1, "quote_a": "Квартира вдовы была на втором этаже",
         "quote_b": "Вера поднялась на третий этаж", "what": "x"},
        "мусор",
    ]
    got = check_against_chapters(4, CH4, [{"number": 3, "content": CH3}], _answer(items))
    assert [g["what"] for g in got] == ["этаж квартиры"]


def test_prompt_shows_previous_chapters_in_full():
    from engine.continuity_checker import check_against_chapters
    seen = {}

    def call(prompt):
        seen["p"] = prompt
        return '{"contradictions": []}'
    prev = [{"number": n, "content": f"текст главы {n}"} for n in range(1, 6)]
    assert check_against_chapters(6, CH4, prev, call) == []
    assert "=== ГЛАВА 5 ===" in seen["p"] and "=== ГЛАВА 3 ===" in seen["p"]
    assert "=== ГЛАВА 2 ===" not in seen["p"] and CH4 in seen["p"]


def test_unparsed_answer_is_an_error_not_silence():
    from engine.continuity_checker import check_against_chapters
    with pytest.raises(ValueError):
        check_against_chapters(4, CH4, [{"number": 3, "content": CH3}], lambda p: "не знаю")


def test_signal_text():
    from engine.continuity_checker import format_cross_signals
    s = format_cross_signals([{"chapter_a": 3, "quote_a": "на втором этаже",
                               "quote_b": "на третий этаж", "what": "этаж квартиры"}])
    assert s == ["Противоречие с главой 3: этаж квартиры («на втором этаже» — здесь «на третий этаж»)."]


# ─── Подключение к движку: только по выбору автора ───────────────────────────

FLOOR = [{"chapter_a": 3, "quote_a": "Квартира вдовы была на втором этаже",
          "quote_b": "Вера поднялась на третий этаж к квартире вдовы", "what": "этаж квартиры"}]


def _checker(items, seen):
    def call(model, system, user, max_tokens=None):
        seen.append(model)
        return json.dumps({"contradictions": items}, ensure_ascii=False)
    return call


def test_no_model_no_call(project_id):
    from engine.continuity_checker import cross_check_signals
    from engine.db_projects import save_chapter
    save_chapter(project_id, 3, CH3, "")
    seen = []
    assert cross_check_signals(project_id, 4, CH4, "nano_gpt::deepseek/deepseek-v4-pro-0813",
                               _checker(FLOOR, seen)) == []
    assert seen == []


def test_chosen_model_checks_against_previous_chapters(project_id):
    from engine.continuity_checker import cross_check_signals
    from engine.db_projects import save_chapter
    from engine.db_settings import set_setting
    save_chapter(project_id, 3, CH3, "")
    set_setting("continuity_model", "chatgpt_subscription::gpt-6.1-sol@medium")
    seen = []
    got = cross_check_signals(project_id, 4, CH4, "nano_gpt::deepseek/deepseek-v4-pro-0813",
                              _checker(FLOOR, seen))
    assert seen == ["chatgpt_subscription::gpt-6.1-sol@medium"]
    assert got == ["Противоречие с главой 3: этаж квартиры («Квартира вдовы была на втором этаже» — "
                   "здесь «Вера поднялась на третий этаж к квартире вдовы»)."]


def test_same_family_warned(project_id):
    from engine.continuity_checker import cross_check_signals
    from engine.db_projects import save_chapter
    from engine.db_settings import set_setting
    save_chapter(project_id, 3, CH3, "")
    set_setting("continuity_model", "nano_gpt::deepseek/deepseek-v4-pro-0813")
    got = cross_check_signals(project_id, 4, CH4, "nano_gpt::deepseek/deepseek-v4-pro-0813",
                              _checker(FLOOR, []))
    assert len(got) == 2 and "того же семейства" in got[0]


def test_checker_failure_is_silent(project_id):
    from engine.continuity_checker import cross_check_signals
    from engine.db_projects import save_chapter
    from engine.db_settings import set_setting
    save_chapter(project_id, 3, CH3, "")
    set_setting("continuity_model", "chatgpt_subscription::gpt-6.1-sol@medium")

    def broken(model, system, user, max_tokens=None):
        raise RuntimeError("codex: usage limit reached")
    assert cross_check_signals(project_id, 4, CH4, "nano_gpt::x", broken) == []


@pytest.fixture
def client():
    import logging
    from web.app import app
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    logging.disable(logging.CRITICAL)
    yield app.test_client()
    logging.disable(logging.NOTSET)


def test_settings_api(client):
    r = client.post("/api/continuity/model", json={"model": "claude_subscription::claude-sonnet-5-5"})
    assert r.get_json()["model"] == "claude_subscription::claude-sonnet-5-5"
    assert client.get("/api/continuity/model").get_json()["model"] == "claude_subscription::claude-sonnet-5-5"
    assert client.post("/api/continuity/model", json={"model": ""}).get_json()["model"] == ""


# ─── Правка по находкам: только с выбранным правщиком ────────────────────────

SOL = "chatgpt_subscription::gpt-6.1-sol@medium"
SONNET = "claude_subscription::claude-sonnet-5-5"
FIXED = "Вера поднялась на второй этаж к квартире вдовы"


def _check_then_fix(seen, left_after_fix=()):
    """Проверяющий: на исходном тексте — FLOOR, на правленом — left_after_fix; правщик — одна замена."""
    def call(model, system, user, max_tokens=None):
        seen.append(model)
        if model == SONNET:
            return json.dumps({"edits": [{"old": "Вера поднялась на третий этаж к квартире вдовы",
                                          "new": FIXED}]}, ensure_ascii=False)
        items = list(left_after_fix) if FIXED in user else FLOOR
        return json.dumps({"contradictions": items}, ensure_ascii=False)
    return call


def _setup(project_id, fixer=SONNET):
    from engine.db_projects import save_chapter
    from engine.db_settings import set_setting
    save_chapter(project_id, 3, CH3, "")
    set_setting("continuity_model", SOL)
    set_setting("continuity_fix_model", fixer)


def test_fixer_edits_and_rechecks(project_id):
    from engine.continuity_checker import cross_check_and_fix
    _setup(project_id)
    seen = []
    text, sig = cross_check_and_fix(project_id, 4, CH4, "nano_gpt::x", _check_then_fix(seen))
    assert FIXED in text and "третий этаж" not in text
    assert seen == [SOL, SONNET, SOL]            # проверка → правка → перепроверка
    assert len(sig) == 1 and "замен 1; не осталось" in sig[0]


def test_what_fix_did_not_remove_stays_a_signal(project_id):
    from engine.continuity_checker import cross_check_and_fix
    _setup(project_id)
    scarf = [{"chapter_a": 3, "quote_a": "красно-чёрный клетчатый шарф",
              "quote_b": "зелёно-сером шарфе", "what": "цвет шарфа"}]
    text, sig = cross_check_and_fix(project_id, 4, CH4, "nano_gpt::x", _check_then_fix([], scarf))
    assert FIXED in text and "осталось 1" in sig[0] and "цвет шарфа" in sig[1]


def test_no_fixer_signals_only(project_id):
    from engine.continuity_checker import cross_check_and_fix
    _setup(project_id, fixer="")
    seen = []
    text, sig = cross_check_and_fix(project_id, 4, CH4, "nano_gpt::x", _check_then_fix(seen))
    assert text == CH4 and seen == [SOL] and sig[0].startswith("Противоречие с главой 3")


def test_fixer_failure_keeps_text_and_signals(project_id):
    from engine.continuity_checker import cross_check_and_fix
    _setup(project_id)
    base = _check_then_fix([])

    def call(model, system, user, max_tokens=None):
        if model == SONNET:
            raise RuntimeError("claude: limit")
        return base(model, system, user, max_tokens)
    text, sig = cross_check_and_fix(project_id, 4, CH4, "nano_gpt::x", call)
    assert text == CH4 and sig[0].startswith("Противоречие с главой 3")


def test_recheck_failure_keeps_fix_and_original_signals(project_id):
    from engine.continuity_checker import cross_check_and_fix
    _setup(project_id)
    base = _check_then_fix([])

    def call(model, system, user, max_tokens=None):
        if model == SOL and FIXED in user:
            raise RuntimeError("codex: limit")
        return base(model, system, user, max_tokens)
    text, sig = cross_check_and_fix(project_id, 4, CH4, "nano_gpt::x", call)
    assert FIXED in text and "перепроверка не удалась" in sig[0] and "этаж квартиры" in sig[1]


def test_cross_check_signals_never_fixes(project_id):
    from engine.continuity_checker import cross_check_signals
    _setup(project_id)
    seen = []
    cross_check_signals(project_id, 4, CH4, "nano_gpt::x", _check_then_fix(seen))
    assert seen == [SOL]


def test_fix_settings_api(client):
    r = client.post("/api/continuity/fix-model", json={"model": SONNET}).get_json()
    assert r["model"] == SONNET
    assert client.get("/api/continuity/fix-model").get_json()["model"] == SONNET
    assert client.post("/api/continuity/fix-model", json={"model": ""}).get_json()["model"] == ""


def test_second_round_fixes_what_recheck_found(project_id):
    from engine.continuity_checker import cross_check_and_fix
    _setup(project_id)
    scarf = [{"chapter_a": 3, "quote_a": "красно-чёрный клетчатый шарф",
              "quote_b": "зелёно-сером шарфе", "what": "цвет шарфа"}]
    seen = []

    def call(model, system, user, max_tokens=None):
        seen.append(model)
        if model == SONNET:
            if "цвет шарфа" in user:
                return json.dumps({"edits": [{"old": "в зелёно-сером шарфе", "new": "в красно-чёрном шарфе"}]},
                                  ensure_ascii=False)
            return json.dumps({"edits": [{"old": "Вера поднялась на третий этаж к квартире вдовы",
                                          "new": FIXED}]}, ensure_ascii=False)
        if "красно-чёрном шарфе" in user:
            return json.dumps({"contradictions": []})
        return json.dumps({"contradictions": scarf if FIXED in user else FLOOR}, ensure_ascii=False)
    text, sig = cross_check_and_fix(project_id, 4, CH4, "nano_gpt::x", call)
    assert FIXED in text and "красно-чёрном шарфе" in text
    assert seen == [SOL, SONNET, SOL, SONNET, SOL]        # два круга правки
    assert sig == ["Правка непрерывности (claude-sonnet-5-5): противоречий с прошлыми главами 2, "
                   "замен 2, кругов 2; не осталось."]


def test_rounds_are_capped(project_id):
    from engine.continuity_checker import CROSS_FIX_ROUNDS, cross_check_and_fix
    _setup(project_id)
    calls = []

    def call(model, system, user, max_tokens=None):
        calls.append(model)
        if model == SONNET:      # каждый раз правит, но проверка всё время что-то находит
            n = sum(1 for m in calls if m == SONNET)
            return json.dumps({"edits": [{"old": "квартире вдовы", "new": f"квартире вдовы{' ' * n}"}]})
        return json.dumps({"contradictions": FLOOR}, ensure_ascii=False)
    cross_check_and_fix(project_id, 4, CH4, "nano_gpt::x", call)
    assert calls.count(SONNET) == CROSS_FIX_ROUNDS
