#!/usr/bin/env python3
"""
Стиль серии (engine/style_profiles.py).

Зачем. 12 стилевых профилей базы движок не читал (AUDIT_UNIFIED.md,
«Справочные файлы»). Теперь стиль выбирается в проекте и идёт в блок
движка отдельным разделом. Проверяется: в промпт не попадают примеры
(модель их копирует) и «Подходит для»; без выбора блок не меняется;
неизвестный стиль не записывается молча.
"""

import sys
from unittest.mock import MagicMock

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())

from engine.style_profiles import (STYLE_HEADER, STYLE_LABELS,  # noqa: E402
                                   list_style_profiles, load_style_profile,
                                   project_style_key)


# ─── Профили ─────────────────────────────────────────────────────────────────

def test_every_label_has_a_profile_file():
    keys = [p["key"] for p in list_style_profiles()]
    assert keys == list(STYLE_LABELS), "профиль без файла или файл без названия"


@pytest.mark.parametrize("key", list(STYLE_LABELS))
def test_section_has_substance_and_no_examples(key):
    text = load_style_profile(key)
    assert text.startswith(f"{STYLE_HEADER}: {STYLE_LABELS[key]}]")
    body = text.split("\n")[2:]
    assert len(body) >= 3, "от профиля осталась пустая шапка"
    lowered = text.lower()
    assert "плохо" not in lowered and "хорошо:" not in lowered, "пример попал в промпт"
    assert "подходит для" not in lowered, "подсказка автору попала в промпт"
    assert "#" not in text and "**" not in text


def test_suits_hint_for_every_profile():
    """Подсказка «подходит для» — на каждом варианте выбора, по-русски."""
    for p in list_style_profiles():
        assert p["suits"], p["key"]
        assert not any(w in p["suits"] for w in ("YA", "fiction", "urban")), p


def test_unknown_or_empty_style_is_nothing():
    assert load_style_profile(None) == ""
    assert load_style_profile("") == ""
    assert load_style_profile("../../00_CORE/META_RULES") == ""
    assert project_style_key({"style_key": "нет_такого"}) is None
    assert project_style_key(None) is None
    assert project_style_key({"style_key": "noir_style"}) == "noir_style"


# ─── Блок движка ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("mode", ["quick", "quality", "master"])
def test_engine_block_gets_style_only_when_chosen(mode):
    from engine.unified_engine import build_engine_context
    plain = build_engine_context("detective_classic", mode, "claude", mode == "master", "")
    styled = build_engine_context("detective_classic", mode, "claude", mode == "master", "",
                                  style_key="noir_style")
    assert STYLE_HEADER not in plain
    assert load_style_profile("noir_style") in styled
    assert styled.index(STYLE_HEADER) > styled.index("=== UNIFIED ENGINE")


def test_generation_context_uses_project_style(project_id):
    from engine.db import get_project, set_project_style_key
    from engine.pipeline_context import _build_engine_block
    set_project_style_key(project_id, "tight_thriller")
    block = _build_engine_block(get_project(project_id), "quick", "claude", "", None)
    assert "[СТИЛЬ СЕРИИ: Сжатый триллер]" in block


# ─── Проект ──────────────────────────────────────────────────────────────────

def test_set_and_clear_style(project_id):
    from engine.db import get_project, set_project_style_key
    set_project_style_key(project_id, "literary")
    assert get_project(project_id)["style_key"] == "literary"
    set_project_style_key(project_id, "")
    assert get_project(project_id)["style_key"] is None


def test_unknown_style_rejected(project_id):
    from engine.db import get_project, set_project_style_key
    with pytest.raises(ValueError):
        set_project_style_key(project_id, "барокко")
    assert get_project(project_id)["style_key"] is None


def test_migration_adds_column_to_old_db(tmp_path, monkeypatch):
    import sqlite3
    import engine.db_core as dbc
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT, genre TEXT)")
    monkeypatch.setattr(dbc, "DB_PATH", db)
    dbc.init_db()
    with sqlite3.connect(db) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(projects)")]
    assert "style_key" in cols


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


def test_main_page_offers_styles_and_saves_choice(client, project_id):
    from engine.db import get_project, set_active_project
    set_active_project(project_id)
    page = client.get("/").get_data(as_text=True)
    assert "Стиль серии" in page and 'value="cinematic"' in page
    client.post("/project/style-key", data={"style_key": "cinematic"})
    assert get_project(project_id)["style_key"] == "cinematic"
    page = client.get("/").get_data(as_text=True)
    assert 'value="cinematic" data-suits' in page and "selected" in page.split('value="cinematic"')[1][:200]


def test_bad_style_from_form_is_not_saved(client, project_id):
    from engine.db import get_project, set_active_project
    set_active_project(project_id)
    client.post("/project/style-key", data={"style_key": "барокко"})
    assert get_project(project_id)["style_key"] is None
