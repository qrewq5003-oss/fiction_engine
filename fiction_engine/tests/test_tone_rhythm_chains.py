#!/usr/bin/env python3
"""
Ритм тона вместо общей нормы и сигнал о цепочках «…, и …, и …».

Зачем.
- У лирики, эпики и экшна свой ритм, а в промпт каждой главы шла общая
  норма («около 30 % коротких», «по этому тебя оценивают»). Две нормы
  спорили: лирика дала среднюю фразу 13.2 слова при ориентире 15–20.
  Для главы с таким тоном общая норма заменяется отсылкой к тону.
- Цепочки «…, и …, и …» — в 22 главах из 24, строкой в антиклише не
  лечатся. Автор получает сигнал, если их больше нормы (одна на страницу).
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())

from engine.genre_mix import MODIFIERS, tone_rhythm_note  # noqa: E402
from engine.pipeline_config import rhythm_rule_for_prompt  # noqa: E402
from engine.pipeline_steps import and_chains_note, find_and_chains  # noqa: E402

RHYTHM_TONES = [k for k, v in MODIFIERS.items() if v.get("rhythm")]


# ─── Ритм ────────────────────────────────────────────────────────────────────

def test_rhythm_tones_are_the_ones_with_numbers():
    assert set(RHYTHM_TONES) == {"lyric", "epic", "action"}


@pytest.mark.parametrize("tone", ["lyric", "epic", "action"])
def test_tone_has_its_own_rhythm_in_its_section(tone):
    from engine.genre_mix import load_chapter_tone_section
    assert "слов" in load_chapter_tone_section(tone), "тон отсылает к ритму, которого у него нет"
    assert MODIFIERS[tone]["label"] in tone_rhythm_note(tone)


def test_other_tones_keep_general_rhythm():
    for t in ("dread", "comedy", "noir", None, "барокко"):
        assert tone_rhythm_note(t) == ""


@pytest.mark.parametrize("mode", ["quick", "quality", "master"])
def test_base_prompt_swaps_rhythm_rule_only_for_that_chapter(project_id, mode):
    from engine.db import get_project, set_chapter_tone
    from engine.state_prompts import build_prompt
    set_chapter_tone(project_id, 3, "lyric")
    project = get_project(project_id)
    lyric = build_prompt(project_id, 3, mode, project)
    plain = build_prompt(project_id, 4, mode, project)
    assert rhythm_rule_for_prompt() in plain
    assert rhythm_rule_for_prompt() not in lyric
    assert "его задаёт тон «Лирика»" in lyric


# ─── Цепочки ─────────────────────────────────────────────────────────────────

CHAIN = "Он встал, и подошёл к окну, и долго смотрел во двор. "
PLAIN = "Он встал и подошёл к окну. Во дворе было пусто. "


def test_counts_chains_and_limit_by_pages():
    text = CHAIN * 4 + PLAIN * 60           # ~640 слов → норма 2
    c = find_and_chains(text)
    assert c["count"] == 4 and c["limit"] == 2 and c["too_many"]
    assert "и подошёл к окну, и долго" in c["examples"][0]


def test_within_norm_no_note():
    assert and_chains_note(CHAIN + PLAIN * 60) == ""
    assert and_chains_note("") == ""


def test_single_and_is_not_a_chain():
    assert find_and_chains(PLAIN * 50)["count"] == 0


def test_note_names_count_norm_and_example():
    note = and_chains_note(CHAIN * 5 + PLAIN * 30)
    assert "Цепочек «…, и …, и …» — 5 при норме до 1" in note
    assert "долго смотрел" in note


def test_run_generation_warns(project_id):
    from engine.pipeline import run_generation
    chapter = (CHAIN * 20 + PLAIN * 350)
    with patch("engine.pipeline._call", return_value=chapter):
        res = run_generation({"id": project_id, "genre": "детектив"}, 1, "quick", "m::x", "Задача.")
    assert "Цепочек «…, и …, и …» — 20" in res["warning"]
    assert res["text"] == chapter, "сигнал, а не правка текста"
