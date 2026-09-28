#!/usr/bin/env python3
"""
Тона (17_TONE_LAYERS) и тон отдельной главы.

Зачем. Комедия как второй слой сработала: обещания 5.25 → 8.42 из 10 в
6 парах из 6 (bench/ab-adherence-comedy-legal-2026-09-28.json). Автор
попросил больше таких слоёв и возможность включать их в отдельные главы:
«детектив + романтика», а седьмая глава ещё и с жутью. Проверяется: тон
доходит до промпта целиком и без примеров, открывает свои жанровые
варианты, живёт за номером главы и не дублирует тон проекта.
"""

import re
import sys
from unittest.mock import MagicMock

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())

from engine.genre_mix import (CHAPTER_TONE_HEADER, MODIFIERS,  # noqa: E402
                              chapter_tone_options, is_chapter_tone,
                              load_chapter_tone_section, load_secondary_section,
                              secondary_options)

TONES = [k for k, v in MODIFIERS.items() if v["chapter"]]


def _block(genre="detective_classic", mode="quality", **kw):
    from engine.unified_engine import build_engine_context
    return build_engine_context(genre, mode, "claude", mode == "master", "", **kw)


def _variants(text, label):
    return len(re.findall(rf"^\*\*{label}[:/]", text, re.M))


# ─── Содержимое ──────────────────────────────────────────────────────────────

def test_nine_chapter_tones_and_ya_is_not_one():
    assert len(TONES) == 9
    assert not is_chapter_tone("young_adult"), "аудитория книги не ставится на главу"
    assert [o["key"] for o in chapter_tone_options()] == TONES


@pytest.mark.parametrize("key", TONES)
def test_tone_section_has_core_techniques_and_mistakes(key):
    text = load_chapter_tone_section(key)
    assert text.startswith(f"{CHAPTER_TONE_HEADER}: {MODIFIERS[key]['label']}]")
    body = text.split("\n")[2:]
    assert len(body) >= 6, "от тона остались крохи"
    assert any(line.startswith("- Избегай:") for line in body), "ошибки не дошли"
    assert "**" not in text and "#" not in text and "Пример" not in text


@pytest.mark.parametrize("key", TONES)
def test_tone_works_for_whole_project_too(key):
    assert load_secondary_section("detective_classic", key).startswith("[ВТОРОЙ ЖАНР")
    assert key in {o["key"] for o in secondary_options()}


# ─── Блок движка ─────────────────────────────────────────────────────────────

def test_no_tone_no_change():
    assert _block() == _block(chapter_tone=None)
    assert CHAPTER_TONE_HEADER not in _block()


def test_tone_on_top_of_project_layer():
    block = _block(secondary_key="romance_contemporary", chapter_tone="dread")
    assert "[ВТОРОЙ ЖАНР: Современная романтика]" in block
    assert "[ТОН ГЛАВЫ: Жуть]" in block
    assert block.index("[ВТОРОЙ ЖАНР") < block.index(CHAPTER_TONE_HEADER)


def test_tone_opens_its_genre_variants():
    plain, dread = _block(), _block(chapter_tone="dread")
    assert _variants(plain, "ХОРРОР") == 0
    assert _variants(dread, "ХОРРОР") > 0
    assert _variants(dread, "РОМАНТИКА") == 0, "тон открывает только свои варианты"


def test_tone_adds_its_modules():
    from engine.unified_engine import _build_module_sections
    names = [n for n, _ in _build_module_sections("quick", "detective_classic", None, "",
                                                  None, None, "action")]
    assert all(m in names for m in MODIFIERS["action"]["modules"])


def test_same_as_project_layer_or_ya_gives_nothing():
    assert load_chapter_tone_section("comedy", project_secondary="comedy") == ""
    assert CHAPTER_TONE_HEADER not in _block(secondary_key="comedy", chapter_tone="comedy")
    assert CHAPTER_TONE_HEADER not in _block(chapter_tone="young_adult")
    assert CHAPTER_TONE_HEADER not in _block(chapter_tone="барокко")


# ─── Глава ───────────────────────────────────────────────────────────────────

def test_tone_is_per_chapter(project_id):
    from engine.db import get_chapter_tone, set_chapter_tone
    set_chapter_tone(project_id, 7, "dread")
    assert get_chapter_tone(project_id, 7) == "dread"
    assert get_chapter_tone(project_id, 8) is None
    set_chapter_tone(project_id, 7, "lyric")
    assert get_chapter_tone(project_id, 7) == "lyric"
    set_chapter_tone(project_id, 7, "")
    assert get_chapter_tone(project_id, 7) is None


def test_bad_tone_rejected(project_id):
    from engine.db import get_chapter_tone, set_chapter_tone
    for bad in ("барокко", "young_adult"):
        with pytest.raises(ValueError):
            set_chapter_tone(project_id, 3, bad)
    assert get_chapter_tone(project_id, 3) is None


def test_generation_context_takes_tone_of_that_chapter(project_id):
    from engine.db import get_project, set_chapter_tone, set_project_genre_key
    from engine.pipeline_context import _build_engine_block
    set_project_genre_key(project_id, "detective_classic")
    set_chapter_tone(project_id, 7, "action")
    project = get_project(project_id)
    assert "[ТОН ГЛАВЫ: Экшн]" in _build_engine_block(project, "quick", "claude", "", None, 7)
    assert CHAPTER_TONE_HEADER not in _build_engine_block(project, "quick", "claude", "", None, 6)


# ─── Страницы ────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    import logging
    from web.app import app
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    logging.disable(logging.CRITICAL)
    yield app.test_client()
    logging.disable(logging.NOTSET)


def test_api_roundtrip(client, project_id):
    from engine.db import set_active_project
    set_active_project(project_id)
    r = client.get("/api/chapter_tone/5").get_json()
    assert r["tone"] is None and [o["key"] for o in r["options"]] == TONES
    assert client.post("/api/chapter_tone/5/save", json={"tone": "noir"}).status_code == 200
    assert client.get("/api/chapter_tone/5").get_json()["tone"] == "noir"
    assert client.post("/api/chapter_tone/5/save", json={"tone": "барокко"}).status_code == 400
    assert client.get("/api/chapter_tone/5").get_json()["tone"] == "noir"


@pytest.mark.parametrize("page,input_id", [("/generate", "gen-chapter"), ("/pipeline", "pl-chapter")])
def test_pages_have_tone_selector(client, project_id, page, input_id):
    from engine.db import set_active_project
    set_active_project(project_id)
    html = client.get(page).get_data(as_text=True)
    assert 'id="chapter-tone-select"' in html
    assert f"getElementById('{input_id}')" in html
