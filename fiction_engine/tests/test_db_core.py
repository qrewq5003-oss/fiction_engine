"""
test_db_core.py — тесты db_core.py

Проверяем: инициализацию схемы, миграции, log_error, get_error_log.
"""

import pytest
import sqlite3
from unittest.mock import patch


def test_init_db_creates_tables(use_temp_db):
    """Все ключевые таблицы создаются при init_db."""
    from engine.db_core import get_conn
    with get_conn() as conn:
        tables = {
            row[0] for row in
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    expected = {
        "projects", "chapters", "state_engine", "state_updates",
        "api_keys", "settings", "generation_history", "symbols",
        "voice_profiles", "pipeline_runs", "pipeline_iterations",
        "l3_memory", "knowledge_base", "engine_error_log", "chapter_analysis",
    }
    assert expected.issubset(tables), f"Отсутствуют таблицы: {expected - tables}"


def test_init_db_idempotent(use_temp_db):
    """Повторный вызов init_db не ломает существующую схему."""
    from engine.db_core import init_db
    init_db()  # второй вызов
    init_db()  # третий — не должно быть ошибок


def test_migrations_are_idempotent(use_temp_db):
    """Миграции можно применять несколько раз."""
    from engine.db_core import _run_migrations
    _run_migrations()
    _run_migrations()
    _run_migrations()


def test_log_error_writes_to_db(use_temp_db):
    """log_error записывает в engine_error_log при падении logger."""
    from engine.db_core import log_error, get_error_log
    with patch("engine.db_core._get_log", side_effect=Exception("logger недоступен")):
        log_error("test context", ValueError("тестовая ошибка"))

    log = get_error_log()
    assert len(log) >= 1
    entry = log[0]
    assert "test context" in entry["context"]
    assert "ValueError" in entry["error"]


def test_log_error_never_raises(use_temp_db):
    """log_error не бросает исключение даже при полной недоступности БД."""
    from engine.db_core import log_error
    with patch("engine.db_core._get_log", side_effect=Exception("упало")):
        with patch("engine.db_core.get_conn", side_effect=Exception("БД недоступна")):
            # Не должно бросить исключение
            log_error("критический контекст", RuntimeError("всё сломалось"))


def test_get_error_log_returns_empty_on_failure(use_temp_db):
    """get_error_log возвращает [] при ошибке БД."""
    from engine.db_core import get_error_log
    with patch("engine.db_core.get_conn", side_effect=sqlite3.Error("нет связи")):
        result = get_error_log()
    assert result == []


def test_get_conn_creates_db_directory(tmp_path):
    """get_conn создаёт директорию если её нет."""
    nested = tmp_path / "a" / "b" / "c" / "test.db"
    with patch("engine.db_core.DB_PATH", nested):
        from engine.db_core import get_conn
        conn = get_conn()
        conn.close()
    assert nested.exists()


def test_default_templates_are_nonempty(use_temp_db):
    """Шаблоны State Engine не пустые."""
    from engine.db_core import _default_global, _default_plot, _default_memory
    assert len(_default_global()) > 50
    assert len(_default_plot()) > 50
    assert len(_default_memory()) > 50
