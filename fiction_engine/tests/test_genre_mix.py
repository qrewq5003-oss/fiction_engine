#!/usr/bin/env python3
"""
Второй жанр проекта (engine/genre_mix.py).

Зачем. Смешение жанров было описано в GENRE_MERGER.md как ручная сборка
списка модулей в коде; в интерфейсе его не было. Комедия и young adult
лежали в базе профилями «для любого жанра» без ключа. Теперь у проекта
есть второй слой: жанр (вторая линия книги) или модификатор (тон,
аудитория). Проверяется: что именно добавляется в блок, что основной
жанр остаётся главным, что без выбора блок не меняется.
"""

import re
import sys
from unittest.mock import MagicMock

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())

from engine.engine_config import GENRE_KEYWORDS, GENRE_MODULES  # noqa: E402
from engine.genre_mix import (MODIFIERS, SECONDARY_HEADER,  # noqa: E402
                              is_secondary_key, load_secondary_section,
                              project_secondary_key, secondary_modules,
                              secondary_options)


def _block(genre, mode="quality", **kw):
    from engine.unified_engine import build_engine_context
    return build_engine_context(genre, mode, "claude", mode == "master", "", **kw)


def _variants(text, label):
    return len(re.findall(rf"^\*\*{label}[:/]", text, re.M))


# ─── Раздел ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("key", sorted(GENRE_KEYWORDS))
def test_every_genre_gives_a_section_with_its_promises(key):
    other = "detective_classic" if key != "detective_classic" else "fantasy_dark"
    text = load_secondary_section(other, key)
    assert text.startswith(SECONDARY_HEADER), key
    assert "Обещания второго жанра:" in text or "Что в нём должно быть:" in text


@pytest.mark.parametrize("key", list(MODIFIERS))
def test_modifier_section_without_examples(key):
    text = load_secondary_section("detective_classic", key)
    assert text.startswith(f"{SECONDARY_HEADER}: {MODIFIERS[key]['label']}]")
    assert "Избегай:" in text, "типичные ошибки не дошли"
    assert "Пример" not in text and "— Нам нужно поговорить" not in text
    assert "###" not in text and "**" not in text


def test_same_as_primary_or_unknown_is_nothing():
    assert load_secondary_section("detective_classic", "detective_classic") == ""
    assert load_secondary_section("detective_classic", "барокко") == ""
    assert load_secondary_section("detective_classic", None) == ""
    assert not is_secondary_key("барокко")
    assert project_secondary_key({"genre_secondary": "comedy"}) == "comedy"
    assert project_secondary_key({"genre_secondary": "x"}) is None


def test_options_list_modifiers_first_then_all_genres():
    opts = secondary_options()
    assert [o["key"] for o in opts[:len(MODIFIERS)]] == list(MODIFIERS)
    assert {o["key"] for o in opts[len(MODIFIERS):]} == set(GENRE_KEYWORDS)


# ─── Блок движка ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("mode", ["quick", "quality", "master"])
def test_no_secondary_no_change(mode):
    assert _block("detective_classic", mode) == _block("detective_classic", mode, secondary_key=None)
    assert SECONDARY_HEADER not in _block("detective_classic", mode)


def test_secondary_genre_adds_section_modules_and_its_variants():
    plain = _block("detective_classic")
    mixed = _block("detective_classic", secondary_key="romance_contemporary")
    assert "[ВТОРОЙ ЖАНР: Современная романтика]" in mixed
    assert _variants(plain, "РОМАНТИКА") == 0
    assert _variants(mixed, "РОМАНТИКА") > 0, "варианты второго семейства отфильтрованы"
    assert _variants(mixed, "ДЕТЕКТИВ") == _variants(plain, "ДЕТЕКТИВ")
    assert _variants(mixed, "ХОРРОР") == 0, "третьи жанры не должны проходить"
    for m in GENRE_MODULES["romance_contemporary"][:2]:
        assert m in secondary_modules("romance_contemporary")


def test_primary_stays_primary():
    """Правила, контракт и арка — от основного жанра."""
    mixed = _block("detective_classic", "master", secondary_key="romance_contemporary")
    assert "ПРАВИЛА ЖАНРА (detective_classic)" in mixed
    assert "ПРАВИЛА ЖАНРА (romance_contemporary)" not in mixed
    assert "=== UNIFIED ENGINE v3 / MASTER / detective_classic ===" in mixed


def test_modifier_adds_its_modules():
    from engine.unified_engine import _build_module_sections
    names = [n for n, _ in _build_module_sections("quick", "detective_classic", None, "", None, "comedy")]
    plain = [n for n, _ in _build_module_sections("quick", "detective_classic", None, "", None)]
    assert all(m in names for m in MODIFIERS["comedy"]["modules"])
    assert set(MODIFIERS["comedy"]["modules"]) - set(plain), "проверка потеряла смысл"


def test_generation_context_uses_project_secondary(project_id):
    from engine.db import get_project, set_project_genre_key, set_project_genre_secondary
    from engine.pipeline_context import _build_engine_block
    set_project_genre_key(project_id, "detective_classic")
    set_project_genre_secondary(project_id, "young_adult")
    block = _build_engine_block(get_project(project_id), "quick", "claude", "", None)
    assert "[ВТОРОЙ ЖАНР: Подростковая проза (YA)]" in block


# ─── Проект ──────────────────────────────────────────────────────────────────

def test_set_and_clear(project_id):
    from engine.db import get_project, set_project_genre_secondary
    set_project_genre_secondary(project_id, "comedy")
    assert get_project(project_id)["genre_secondary"] == "comedy"
    set_project_genre_secondary(project_id, "")
    assert get_project(project_id)["genre_secondary"] is None


def test_rejects_unknown_and_same_as_primary(project_id):
    from engine.db import get_project, set_project_genre_key, set_project_genre_secondary
    set_project_genre_key(project_id, "fantasy_dark")
    with pytest.raises(ValueError):
        set_project_genre_secondary(project_id, "барокко")
    with pytest.raises(ValueError):
        set_project_genre_secondary(project_id, "fantasy_dark")
    assert get_project(project_id)["genre_secondary"] is None


def test_migration_adds_column(tmp_path, monkeypatch):
    import sqlite3
    import engine.db_core as dbc
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT, genre TEXT)")
    monkeypatch.setattr(dbc, "DB_PATH", db)
    dbc.init_db()
    with sqlite3.connect(db) as conn:
        assert "genre_secondary" in [r[1] for r in conn.execute("PRAGMA table_info(projects)")]


# ─── Страница ────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    import logging
    from web.app import app
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    logging.disable(logging.CRITICAL)
    yield app.test_client()
    logging.disable(logging.NOTSET)


def test_main_page_offers_and_saves(client, project_id):
    from engine.db import get_project, set_active_project, set_project_genre_key
    set_active_project(project_id)
    set_project_genre_key(project_id, "detective_classic")
    page = client.get("/").get_data(as_text=True)
    assert "Второй жанр" in page and 'label="Тон и аудитория"' in page
    assert page.index('label="Тон и аудитория"') < page.index('label="Жанры"')
    card = page[page.index("🧬 Второй жанр"):page.index("🖋 Стиль серии")]
    assert 'value="detective_classic"' not in card, "основной жанр предложен вторым"
    client.post("/project/genre-secondary", data={"genre_secondary": "romance_contemporary"})
    assert get_project(project_id)["genre_secondary"] == "romance_contemporary"


def test_bad_value_from_form_not_saved(client, project_id):
    from engine.db import get_project, set_active_project
    set_active_project(project_id)
    client.post("/project/genre-secondary", data={"genre_secondary": "барокко"})
    assert get_project(project_id)["genre_secondary"] is None
