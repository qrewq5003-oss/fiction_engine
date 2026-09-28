#!/usr/bin/env python3
"""
Критик и судья знают второй слой книги и тон главы.

Зачем. Генератор получает «[ТОН ГЛАВЫ: Лирика]», а критик и судья видели
только основной жанр: лирическая глава в триллере для них «провисает»,
жуть в детективе «уходит от жанра» — оценка снижалась за то, что автор
выбрал нарочно. Справка genre_mix.review_layers_note говорит им, что
выбрано и что проверять: удался ли слой.
"""

import sys
from unittest.mock import MagicMock, patch

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())

from engine.genre_mix import REVIEW_LAYERS_HEADER, review_layers_note  # noqa: E402

TEXT = "Она закрыла дверь и села у окна. " * 60
CRITIC_REPLY = ("ГОЛОС: 7/10\nСТРУКТУРА: 7/10\nПЕРСОНАЖИ: 7/10\nСЦЕНЫ: 7/10\n"
                "ДИАЛОГ: 7/10\nИТОГО: 35/50\nВЕРДИКТ: ПРИНЯТЬ")


def _project(project_id, secondary=None, tone=None, chapter=4):
    from engine.db import (get_project, set_chapter_tone, set_project_genre_key,
                           set_project_genre_secondary)
    set_project_genre_key(project_id, "thriller_psychological")
    set_project_genre_secondary(project_id, secondary)
    set_chapter_tone(project_id, chapter, tone)
    return get_project(project_id)


# ─── Справка ─────────────────────────────────────────────────────────────────

def test_no_layers_no_note(project_id):
    assert review_layers_note(_project(project_id), 4) == ""
    assert review_layers_note(None, 4) == ""


def test_note_names_book_layer_and_chapter_tone(project_id):
    note = review_layers_note(_project(project_id, "romance_contemporary", "lyric"), 4)
    assert note.startswith(REVIEW_LAYERS_HEADER)
    assert "Второй жанр книги: Современная романтика" in note
    assert "Тон этой главы: Лирика" in note and "не снижает оценку" in note


def test_tone_only_for_its_chapter(project_id):
    project = _project(project_id, None, "dread", chapter=4)
    assert "Жуть" in review_layers_note(project, 4)
    assert review_layers_note(project, 5) == ""


def test_book_tone_not_repeated_as_chapter_tone(project_id):
    note = review_layers_note(_project(project_id, "comedy", "comedy"), 4)
    assert "Тон всей книги: Комедия" in note
    assert "Тон этой главы" not in note


# ─── Критик, судья, оценка ───────────────────────────────────────────────────

class Capture:
    def __init__(self):
        self.calls = []

    def __call__(self, model, system, user, max_tokens=None, prefill=""):
        self.calls.append({"system": system, "user": user})
        return CRITIC_REPLY


def test_critic_gets_layers(project_id):
    from engine.pipeline_steps import step_critique
    _project(project_id, None, "lyric")
    call = Capture()
    with patch("engine.pipeline_steps.save_pipeline_iteration"):
        step_critique(1, 1, 4, "m", call, {"generated_text": TEXT}, project_id=project_id,
                      genre="thriller_psychological")
    assert "Тон этой главы: Лирика" in call.calls[0]["user"]


def test_judge_gets_layers_with_contract_clause(project_id):
    from engine.pipeline_steps import step_judge
    _project(project_id, None, "dread")
    call = Capture()
    with patch("engine.pipeline_steps.save_pipeline_iteration"):
        step_judge(1, 1, 4, "m", call, {"generated_text": TEXT, "critique": CRITIC_REPLY},
                   project_id=project_id, genre_key="thriller_psychological")
    system = call.calls[0]["system"]
    assert "Тон этой главы: Жуть" in system
    assert "не нарушение контракта" in system


def test_critic_without_layers_unchanged(project_id):
    from engine.pipeline_steps import step_critique
    _project(project_id)
    call = Capture()
    with patch("engine.pipeline_steps.save_pipeline_iteration"):
        step_critique(1, 1, 4, "m", call, {"generated_text": TEXT}, project_id=project_id)
    assert REVIEW_LAYERS_HEADER not in call.calls[0]["user"]


def test_score_text_puts_layers_before_chapter():
    from engine.pipeline import score_text
    call = Capture()
    with patch("engine.pipeline._call", side_effect=call):
        score_text(TEXT, "thriller_psychological", "m", layers="СЛОИ ГЛАВЫ (…):\n- Тон этой главы: Экшн")
    user = call.calls[0]["user"]
    assert user.index("Тон этой главы: Экшн") < user.index("Глава:")


def test_auto_score_after_save_passes_layers(project_id):
    from web.blueprints.helpers import _auto_score_chapter
    _project(project_id, None, "noir", chapter=4)
    seen = {}

    def fake_score(text, genre, model, layers=""):
        seen["layers"] = layers
        return {"total": 35}

    with patch("engine.pipeline.score_text", side_effect=fake_score), \
         patch("engine.db.get_api_key", return_value="k"):
        _auto_score_chapter(project_id, 4, TEXT, "anthropic::claude-test")
    assert "Тон этой главы: Нуар" in seen["layers"]
