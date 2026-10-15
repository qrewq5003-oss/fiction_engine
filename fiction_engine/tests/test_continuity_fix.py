"""Точечная правка по находкам проверки непрерывности: замены, а не переписывание."""
import json

import pytest

from engine.continuity_fix import (apply_edits, changed_share, fix_contradictions,
                                   quote_context)

TEXT = ("Вера вошла в контору. «Ты вчера оборвала звонок», — сказала она.\n\n"
        "Ирина молчала. На столе лежала программка — вчерашняя, «Маскарад».")


def test_exact_edit_applied_once():
    out, ok, bad = apply_edits(TEXT, [{"old": "Ты вчера оборвала звонок", "new": "Ты утром оборвала звонок"}])
    assert "Ты утром оборвала звонок" in out and "вчера оборвала" not in out
    assert len(ok) == 1 and not bad


def test_flexible_match_on_spaces_and_quotes():
    # Модель переписала кавычки и схлопнула перенос — фрагмент всё равно находится
    out, ok, bad = apply_edits(TEXT, [{"old": "\"Ты  вчера оборвала звонок\", - сказала она.",
                                       "new": "«Ты утром оборвала звонок», — сказала она."}])
    assert "утром оборвала" in out and len(ok) == 1 and not bad


def test_dash_dialogue_matches_quoted_fragment():
    # В главе реплика с тире, модель процитировала её в кавычках
    text = "— Вы тот самый человек, который приходил вечером? — спросила Вера."
    out, ok, bad = apply_edits(text, [{"old": "«Вы тот самый человек, который приходил вечером?»",
                                       "new": "«Вы тот самый человек, который приходил утром?»"}])
    assert "приходил утром" in out and ok[0]["way"] == "words" and not bad


def test_anchored_by_first_and_last_sentence():
    # Середину фрагмента модель пересказала — находим по краям
    text = "Высокий. Синий костюм. Волосы с проседью, лицо спокойное. Он стоял и смотрел, а потом ушёл. Конец."
    old = "Высокий. Синий костюм. Лицо очень спокойное. Он стоял и смотрел, а потом ушёл."
    out, ok, bad = apply_edits(text, [{"old": old, "new": "Высокий. Он ушёл."}])
    assert out == "Высокий. Он ушёл. Конец." and ok[0]["way"] == "anchored"


def test_missing_fragment_is_reported_not_applied():
    out, ok, bad = apply_edits(TEXT, [{"old": "этого в главе нет", "new": "что-то"},
                                      {"old": "", "new": "пусто"}])
    assert out == TEXT and not ok and len(bad) == 2
    assert bad[0]["why"] == "не найдено в главе"


def test_overlapping_edit_is_reported_as_overlapped():
    out, ok, bad = apply_edits(TEXT, [{"old": "Ты вчера оборвала звонок", "new": "Ты утром оборвала звонок"},
                                      {"old": "«Ты вчера оборвала звонок», — сказала она.",
                                       "new": "«Ты оборвала звонок», — сказала она."}])
    assert len(ok) == 1 and bad[0]["why"] == "перекрыто другой заменой"


def test_quote_context_window():
    ctx = quote_context(TEXT, "лежала программка", radius=12)
    assert "программка" in ctx and len(ctx) < 60
    assert quote_context(TEXT, "нет такой цитаты") == ""


def test_fix_builds_prompt_and_applies(monkeypatch):
    seen = {}

    def fake(prompt):
        seen["prompt"] = prompt
        return json.dumps({"edits": [{"old": "Ты вчера оборвала звонок", "new": "Ты утром оборвала звонок"}]})

    found = [{"chapter_a": 3, "quote_a": "Я задала вам вопрос утром",
              "quote_b": "Ты вчера оборвала звонок", "what": "Звонок был утром, а не вчера."}]
    prev = [{"number": 3, "content": "Утро. Я задала вам вопрос утром. Вы не ответили, Ирина."}]
    r = fix_contradictions(4, TEXT, found, prev, fake)
    assert "утром оборвала" in r["text"] and len(r["applied"]) == 1
    assert "Как это было в главе 3" in seen["prompt"] and "Звонок был утром" in seen["prompt"]
    assert "=== ГЛАВА 4 ===" in seen["prompt"]


def test_no_findings_no_call():
    r = fix_contradictions(4, TEXT, [], [], lambda p: pytest.fail("вызова быть не должно"))
    assert r["text"] == TEXT and r["edits"] == []


def test_unparsable_answer_raises():
    with pytest.raises(ValueError):
        fix_contradictions(4, TEXT, [{"chapter_a": 3, "quote_a": "а", "quote_b": "б", "what": "в"}],
                           [], lambda p: "не json")


def test_changed_share():
    assert changed_share("а б в г", "а б в г") == 0.0
    assert changed_share("а б в г", "а б х г") == 0.25


def test_self_contradictions_both_quotes_must_be_in_chapter():
    from engine.continuity_checker import check_self_contradictions
    text = ("Вера поднялась на третий этаж. Дверь была приоткрыта.\n\n"
            "Через час она снова стояла у двери на втором этаже и слушала тишину.")
    raw = json.dumps({"contradictions": [
        {"quote_a": "поднялась на третий этаж", "quote_b": "у двери на втором этаже", "what": "Этаж сменился."},
        {"quote_a": "этого в главе нет никак", "quote_b": "у двери на втором этаже", "what": "мимо"}]})
    found = check_self_contradictions(5, text, lambda p: raw)
    assert len(found) == 1 and found[0]["chapter_a"] == 5 and found[0]["what"] == "Этаж сменился."
    assert check_self_contradictions(5, "", lambda p: pytest.fail("вызова быть не должно")) == []
