"""
Общие фикстуры тестов планировщика.

Каждый тест получает свою временную БД: PLANNER_DB читается модулем
engine.db при импорте, поэтому переменная выставляется до него, а путь
модуля подменяется для уже импортированных случаев.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


REAL_DB = (ROOT / "planner.db").resolve()


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db = tmp_path / "planner.db"
    monkeypatch.setenv("PLANNER_DB", str(db))

    import engine.db as db_mod
    monkeypatch.setattr(db_mod, "DB_PATH", str(db))

    # Предохранитель: рабочая БД пользователя лежит рядом с кодом, и путь
    # к ней вычисляется относительно модуля. Если подмена когда-нибудь
    # перестанет срабатывать, тест обязан упасть, а не переписать данные.
    assert Path(db_mod.DB_PATH).resolve() != REAL_DB, (
        "тесты нацелились на рабочую БД планировщика"
    )

    import engine.migrations as mig
    monkeypatch.setattr(mig, "DB_PATH", str(db), raising=False)

    db_mod.init_db()
    return db


@pytest.fixture
def project_id():
    from engine.db import create_project
    return create_project("Тестовый", "детектив", "описание")


@pytest.fixture
def client(temp_db):
    """Flask-клиент планировщика."""
    import app as planner_app
    planner_app.app.config["TESTING"] = True
    planner_app.app.config["SECRET_KEY"] = "test"
    return planner_app.app.test_client()


@pytest.fixture(autouse=True)
def real_db_untouched():
    """
    Рабочая БД не должна меняться ни одним тестом.

    Проверяется до и после каждого теста: при любом изменении файла тест
    падает. Поводом стал случай, когда planner.db оказалась пустой —
    причину установить не удалось, и такая проверка снимает вопрос
    навсегда.
    """
    import hashlib

    def digest():
        if not REAL_DB.exists():
            return None
        return hashlib.sha256(REAL_DB.read_bytes()).hexdigest()

    before = digest()
    yield
    assert digest() == before, "тест изменил рабочую planner.db"
