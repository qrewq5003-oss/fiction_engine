#!/usr/bin/env python3
"""
Требование объёма одинаково во всех промптах генерации.

Промптов три — quick, quality, master, — и требование объёма в каждом
своё, набранное руками. Разойтись им ничего не мешало, и они разошлись:
quick просил «2500-3000 слов (считай абзацы — их должно быть 15-20)»,
то есть 125-200 слов на абзац, а два других на тот же объём — 25-35
абзацев. Одно и то же требование в двух арифметиках.

Тест перебирает СБОРЩИКИ промптов, а не их список: новый режим попадёт
под проверку сам.

Что здесь НЕ проверяется — сколько слов выдаст модель. Это свойство
модели, а не промпта: замер 2026-09-12 показал, что haiku упирается
около 1900-2000 за вызов при любой формулировке, а бюджет токенов
(11730) не расходуется и наполовину.
"""

import re
import sys
from unittest.mock import MagicMock

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())
sys.modules["openai"].OpenAI = MagicMock()

MODES = ("quick", "quality", "master")


def _prompts() -> dict[str, str]:
    """Собранный промпт каждого режима — через публичный build_prompt."""
    from engine.state_prompts import build_prompt
    project = {"id": 1, "name": "Проект", "genre": "детектив"}
    return {mode: build_prompt(1, 3, mode, project) for mode in MODES}


@pytest.fixture
def prompts(monkeypatch):
    import tempfile
    from pathlib import Path
    import engine.db_core as dbc
    monkeypatch.setattr(dbc, "DB_PATH", Path(tempfile.mkdtemp()) / "fe.db")
    from engine.db_core import init_db
    init_db()
    from engine.db import create_project
    create_project("Проект", "детектив")
    return _prompts()


def test_every_mode_states_the_word_target(prompts):
    for mode, text in prompts.items():
        assert re.search(r"2500-3000 слов", text), f"{mode}: нет требования объёма"


def test_paragraph_ranges_agree_across_modes(prompts):
    """
    Одно требование — одна арифметика. Расхождение 15-20 против 25-35
    означало, что в quick абзац втрое длиннее, чем в остальных.
    """
    ranges = {}
    for mode, text in prompts.items():
        m = re.search(r"\((\d+)-(\d+) абзацев\)", text)
        assert m, f"{mode}: не сказано, сколько абзацев"
        ranges[mode] = (int(m.group(1)), int(m.group(2)))
    assert len(set(ranges.values())) == 1, f"режимы расходятся в абзацах: {ranges}"


def test_paragraph_range_is_arithmetically_possible(prompts):
    """
    Слов на абзац должно получаться правдоподобно. 2500-3000 слов в
    15-20 абзацах — это 125-200 слов на абзац; в текстах прогона выходило
    20-30. Верхняя граница держит формулировку в пределах разумного.
    """
    text = prompts["quick"]
    words = [int(x) for x in re.search(r"(\d+)-(\d+) слов", text).groups()]
    paras = [int(x) for x in re.search(r"\((\d+)-(\d+) абзацев\)", text).groups()]
    per_para = words[1] / paras[0]
    assert per_para <= 120, (
        f"{per_para:.0f} слов на абзац — столько не пишут; "
        "требование объёма и требование абзацев противоречат друг другу")


def test_every_mode_asks_the_model_to_check_its_own_length(prompts):
    """
    Самопроверка перед финалом. На голом запросе она давала +20%
    (1599 → 1925 слов, haiku 4.5); на полном промпте движка прирост
    оказался куда меньше — 1196 → 1209 и 1295 → 1417. Оставлена потому,
    что не вредит, но обещать по ней ничего нельзя.
    """
    for mode, text in prompts.items():
        assert "проверь себя" in text, f"{mode}: нет самопроверки объёма"
        assert "2500" in text.split("проверь себя")[1][:160], \
            f"{mode}: самопроверка не называет число"
