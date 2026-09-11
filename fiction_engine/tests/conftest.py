"""
conftest.py — общие pytest-фикстуры.

Используют in-memory SQLite, чтобы тесты:
  - не трогали реальную БД
  - работали изолированно
  - запускались без настроек окружения
"""

import sys
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Добавляем корень проекта в sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ─── Заглушки внешних зависимостей ───────────────────────────────────────────
# openai и anthropic требуют установки, но тесты не делают реальных LLM-вызовов.
# Ставим моки ДО любого импорта engine.* — иначе engine/api.py упадёт при импорте.
# Если пакеты уже установлены — моки не перезаписывают их (setdefault).
sys.modules.setdefault("openai", MagicMock())
sys.modules.setdefault("anthropic", MagicMock())
# Некоторые модули делают from openai import OpenAI — мок должен поддерживать это
if not hasattr(sys.modules["openai"], "OpenAI"):
    sys.modules["openai"].OpenAI = MagicMock()


@pytest.fixture(autouse=True)
def use_temp_db(tmp_path):
    """
    Каждый тест получает свою in-memory БД.
    Патчим DB_PATH до импорта модулей движка.
    """
    db_file = tmp_path / "test.db"
    with patch("engine.db_core.DB_PATH", db_file):
        from engine.db_core import init_db
        init_db()
        yield db_file


@pytest.fixture
def project_id(use_temp_db):
    """Создаёт тестовый проект и возвращает его ID."""
    from engine.db_projects import create_project
    return create_project("Тестовый проект", "фэнтези")


@pytest.fixture
def project_with_chapters(project_id):
    """Проект с тремя главами."""
    from engine.db_projects import save_chapter
    save_chapter(project_id, 1, "Глава первая. Герой вышел из дому.", "Начало")
    save_chapter(project_id, 2, "Глава вторая. Герой встретил дракона.", "Встреча")
    save_chapter(project_id, 3, "Глава третья. Герой победил.", "Победа")
    return project_id


# ─── Временные каталоги ───────────────────────────────────────────────────────
#
# Несколько тестов зовут tempfile.mkdtemp() напрямую, минуя фикстуру tmp_path.
# Каталоги при этом не удаляются: hypothesis прогоняет тело сотни раз, и один
# прогон набора оставлял тысячи каталогов. Наблюдалось 19 590 штук — /tmp на
# 7 ГБ забивался под завязку и ронял посторонние команды.
#
# Подменяем mkdtemp на версию, которая складывает всё под один корень,
# удаляемый в конце сессии. Вызовы в тестах менять не нужно.

import atexit
import shutil
import tempfile as _tempfile

_TESTS_TMP_ROOT = _tempfile.mkdtemp(prefix="fe_pytest_")
_real_mkdtemp = _tempfile.mkdtemp


def _scoped_mkdtemp(suffix=None, prefix=None, dir=None):
    return _real_mkdtemp(suffix=suffix, prefix=prefix,
                         dir=dir if dir is not None else _TESTS_TMP_ROOT)


_tempfile.mkdtemp = _scoped_mkdtemp
atexit.register(lambda: shutil.rmtree(_TESTS_TMP_ROOT, ignore_errors=True))
