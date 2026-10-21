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

# Тесты не ходят в настоящий FE на :5000 с настоящим токеном и не пишут ключ
# сессий в домашнюю папку (разбор планировщика 21.10). Тесты связки с FE
# поднимают свою заглушку и задают FE_URL сами
_iso = tempfile.mkdtemp(prefix="planner_test_")
os.environ.setdefault("FE_URL", "http://127.0.0.1:1")
os.environ.setdefault("FE_API_TOKEN_FILE", os.path.join(_iso, "api_token"))
os.environ.setdefault("PLANNER_SECRET_FILE", os.path.join(_iso, "secret.key"))
Path(os.environ["FE_API_TOKEN_FILE"]).write_text("test-token", encoding="utf-8")


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
def client(temp_db, monkeypatch):
    """Flask-клиент планировщика: без пароля и без проверки CSRF (её — test_security)."""
    monkeypatch.delenv("PLANNER_PASSWORD", raising=False)
    monkeypatch.delenv("FE_PASSWORD", raising=False)
    import app as planner_app
    planner_app.app.config["TESTING"] = True
    planner_app.app.config["SECRET_KEY"] = "test"
    planner_app.app.config["PLANNER_CSRF"] = False
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
