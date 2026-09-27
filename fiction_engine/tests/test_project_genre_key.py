#!/usr/bin/env python3
"""
Жанр движка хранится в проекте, а не угадывается при каждой генерации.

Зачем. Жанр определялся из свободного текста projects.genre на каждом
вызове, и ошибка определения меняла весь жанровый блок: каталог,
контракт, профиль, арку и модули (AUDIT_UNIFIED.md, U2). Хуже того,
часть потребителей получала сам текст («городское фэнтези») и делила его
по «_»: судья не получал жанровый контракт, а калибровка напряжения и
жанровые усилители маршрутизатора не срабатывали ни в одном
русскоязычном проекте.

Теперь автор выбирает ключ жанра, а все потребители берут его через
project_genre_key(). Пока ключ не выбран, работает прежнее
автоопределение, и главная страница просит его подтвердить.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())
sys.modules["openai"].OpenAI = MagicMock()

KB_PATH = Path(__file__).resolve().parents[2] / "UNIFIED_ENGINE_MASTER"


# ─── Хранение ────────────────────────────────────────────────────────────────

class TestStorage:
    def test_column_exists_after_init(self):
        from engine.db_core import get_conn
        with get_conn() as conn:
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(projects)")}
        assert "genre_key" in cols

    def test_migration_adds_column_to_old_db(self, tmp_path):
        """База, созданная до появления колонки, получает её при старте."""
        import sqlite3
        from unittest.mock import patch
        db_file = tmp_path / "old.db"
        conn = sqlite3.connect(db_file)
        conn.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                     "name TEXT NOT NULL UNIQUE, genre TEXT, "
                     "created_at TEXT DEFAULT (datetime('now')), config TEXT DEFAULT '{}')")
        conn.execute("INSERT INTO projects (name, genre) VALUES ('Старый', 'детектив')")
        conn.commit()
        conn.close()
        with patch("engine.db_core.DB_PATH", db_file):
            from engine.db_core import init_db
            from engine.db_projects import get_project
            init_db()
            project = get_project(1)
        assert project["genre_key"] is None
        assert project["genre"] == "детектив"

    def test_create_without_key_leaves_it_unset(self):
        from engine.db_projects import create_project, get_project
        pid = create_project("Без ключа", "детектив")
        assert get_project(pid)["genre_key"] is None

    def test_create_with_key(self):
        from engine.db_projects import create_project, get_project
        pid = create_project("С ключом", "про ведьм", "fantasy_urban")
        assert get_project(pid)["genre_key"] == "fantasy_urban"

    def test_create_rejects_unknown_key(self):
        from engine.db_projects import create_project, get_projects
        with pytest.raises(ValueError):
            create_project("Плохой", "", "no_such_genre")
        assert not [p for p in get_projects() if p["name"] == "Плохой"]

    def test_set_and_clear(self, project_id):
        from engine.db_projects import get_project, set_project_genre_key
        set_project_genre_key(project_id, "horror_gothic")
        assert get_project(project_id)["genre_key"] == "horror_gothic"
        set_project_genre_key(project_id, "")
        assert get_project(project_id)["genre_key"] is None

    def test_set_rejects_unknown_key(self, project_id):
        from engine.db_projects import get_project, set_project_genre_key
        set_project_genre_key(project_id, "horror_gothic")
        with pytest.raises(ValueError):
            set_project_genre_key(project_id, "horror")
        assert get_project(project_id)["genre_key"] == "horror_gothic"


# ─── Определение жанра проекта ───────────────────────────────────────────────

class TestProjectGenreKey:
    def test_chosen_key_wins_over_text(self):
        from engine.unified_engine import project_genre_key
        project = {"genre": "космическая опера", "genre_key": "horror_gothic"}
        assert project_genre_key(project) == "horror_gothic"

    def test_unset_key_falls_back_to_detection(self):
        from engine.unified_engine import project_genre_key
        assert project_genre_key({"genre": "космическая опера", "genre_key": None}) \
            == "scifi_space_opera"

    def test_stale_key_falls_back_to_detection(self):
        """Ключ, которого больше нет в конфиге, не должен попасть в движок."""
        from engine.unified_engine import project_genre_key
        assert project_genre_key({"genre": "нуар", "genre_key": "removed_genre"}) \
            == "detective_noir"

    def test_no_project(self):
        from engine.unified_engine import project_genre_key
        assert project_genre_key(None) is None

    def test_detect_genre_passes_key_through(self):
        """Ключ можно отдавать туда, куда раньше шёл текст жанра."""
        from engine.engine_config import GENRE_KEYWORDS
        from engine.unified_engine import detect_genre
        for key in GENRE_KEYWORDS:
            assert detect_genre(key) == key


# ─── Потребители получают ключ ───────────────────────────────────────────────

class TestConsumersGetKey:
    def test_engine_block_built_for_chosen_key(self, monkeypatch):
        import engine.pipeline_context as pc
        seen = {}

        def fake_build(genre, mode, **kw):
            seen["genre"] = genre
            return "ENGINE"

        monkeypatch.setattr(pc, "build_engine_context", fake_build)
        project = {"id": 1, "genre": "про любовь", "genre_key": "horror_gothic"}
        assert pc._build_engine_block(project, "quick", "", "", None) == "ENGINE"
        assert seen["genre"] == "horror_gothic"

    def test_judge_gets_genre_contract_for_russian_genre(self, monkeypatch):
        """
        Судья получал текст «городское фэнтези» вместо ключа; загрузчик
        контракта делил его по «_» и не находил семейство — контракта не было.
        """
        assert KB_PATH.is_dir(), f"нет базы: {KB_PATH}"
        import engine.engine_loaders as loaders
        from engine.unified_engine import project_genre_key
        monkeypatch.setattr(loaders, "get_engine_path", lambda: KB_PATH)
        key = project_genre_key({"genre": "городское фэнтези", "genre_key": None})
        assert loaders._load_genre_contract(key).strip()
        assert loaders._load_genre_contract("городское фэнтези") == ""

    def test_tension_calibration_uses_genre_family(self, project_id, monkeypatch):
        """
        Калибровка напряжения делила по «_» русский текст жанра и всегда
        брала цели «default». Теперь она видит семейство из ключа.
        """
        import engine.narrative_intelligence as ni
        from engine.db_projects import set_project_genre_key
        set_project_genre_key(project_id, "thriller_spy")

        class _Stop(Exception):
            pass

        seen = {}

        def spy(*a, **kw):
            seen["family"] = kw.get("genre_family")
            raise _Stop

        monkeypatch.setattr(ni, "_generate_warnings", spy)
        nil = ni.NarrativeIntelligence(
            get_summaries_fn=lambda *a, **k: [{"chapter_num": 1}],
            get_state_fn=lambda *a, **k: {},
            get_chapters_fn=lambda *a, **k: [],
        )
        for name, value in [("_extract_mood_trajectory", []),
                            ("_extract_conflict_density", ([], 0.0)),
                            ("_track_promises", {}),
                            ("_analyze_arcs", {}),
                            ("_detect_contradictions", [])]:
            monkeypatch.setattr(nil, name, lambda *a, _v=value, **k: _v)
        with pytest.raises(_Stop):
            nil.analyze(project_id, 1, lambda prompt: "")
        assert seen["family"] == "thriller"


# ─── Интерфейс ───────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    import logging
    from web.app import app
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    logging.disable(logging.CRITICAL)
    yield app.test_client()
    logging.disable(logging.NOTSET)


class TestWeb:
    def _active(self, name="Проект", genre="детектив", key=None):
        from engine.db import create_project, set_active_project
        pid = create_project(name, genre, key)
        set_active_project(pid)
        return pid

    def test_new_project_with_key(self, client):
        from engine.db_projects import get_projects
        client.post("/project/new", data={"name": "Новый", "genre": "про ведьм",
                                          "genre_key": "fantasy_urban"})
        p = next(p for p in get_projects() if p["name"] == "Новый")
        assert p["genre_key"] == "fantasy_urban"

    def test_new_project_auto_leaves_key_unset(self, client):
        from engine.db_projects import get_projects
        client.post("/project/new", data={"name": "Авто", "genre": "детектив",
                                          "genre_key": ""})
        p = next(p for p in get_projects() if p["name"] == "Авто")
        assert p["genre_key"] is None

    def test_set_key_for_active_project(self, client):
        from engine.db_projects import get_project
        pid = self._active()
        client.post("/project/genre-key", data={"genre_key": "detective_noir"})
        assert get_project(pid)["genre_key"] == "detective_noir"

    def test_set_unknown_key_is_rejected(self, client):
        from engine.db_projects import get_project
        pid = self._active(key="detective_noir")
        r = client.post("/project/genre-key", data={"genre_key": "bogus"},
                        follow_redirects=True)
        assert r.status_code == 200
        assert get_project(pid)["genre_key"] == "detective_noir"

    def test_index_asks_to_confirm_when_unset(self, client):
        self._active(genre="космическая опера")
        html = client.get("/").get_data(as_text=True)
        assert "Жанр не выбран" in html
        # Предложено то, что движок определил по тексту жанра
        import re
        assert re.search(r'value="scifi_space_opera"\s*selected', html)

    def test_index_quiet_when_set(self, client):
        self._active(key="scifi_space_opera")
        html = client.get("/").get_data(as_text=True)
        assert "Жанр не выбран" not in html
