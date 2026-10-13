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
