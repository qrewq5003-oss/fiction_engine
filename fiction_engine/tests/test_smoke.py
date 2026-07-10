"""
test_smoke.py — smoke-тесты Flask-приложения.

Что проверяем:
  - приложение импортируется без ошибок
  - init_db() создаёт все ожидаемые таблицы
  - ключевые API-роуты отвечают (не 500)
  - создание/получение/удаление проекта через HTTP
  - активный проект сохраняется между запросами
  - /api/models возвращает список моделей
  - /api/engine/status возвращает JSON со статусом
  - /api/chapters без проекта возвращает пустой список, не ошибку
  - /api/settings/prevalidation GET и POST работают
  - before_request hook validate_engine_once не падает

Smoke-тесты намеренно не проверяют бизнес-логику — только что
роуты живые и не падают с 500. Полная логика — в test_pipeline_integration.py.

Запуск:
    python -m pytest tests/test_smoke.py -v
    # или без pytest:
    python tests/test_smoke.py
"""

import sys
import os
import unittest
import tempfile
import pathlib
from unittest.mock import MagicMock, patch

# ─── Моки внешних зависимостей (до импорта engine) ───────────────────────────
sys.modules.setdefault("openai", MagicMock())
sys.modules.setdefault("anthropic", MagicMock())
if not hasattr(sys.modules["openai"], "OpenAI"):
    sys.modules["openai"].OpenAI = MagicMock()

# Корень проекта
ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))


# ─── Базовый класс с изолированной БД и Flask test client ────────────────────

class SmokeBase(unittest.TestCase):
    """
    Каждый тест-класс получает свою временную БД и Flask test client.
    """

    def setUp(self):
        self._tmp_dir = tempfile.mkdtemp()
        self._db_path = pathlib.Path(self._tmp_dir) / "test.db"
        self._db_patcher = patch("engine.db_core.DB_PATH", self._db_path)
        self._db_patcher.start()

        os.environ.setdefault("FLASK_SECRET_KEY", "smoke-test-secret")

        from engine.db_core import init_db
        init_db()

        # Импортируем app каждый раз заново чтобы before_request сбросился
        import importlib
        import web.app as webapp
        # Сбрасываем флаг валидации движка чтобы не зависеть от порядка тестов
        webapp._engine_validated = False

        self.app = webapp.app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        self._db_patcher.stop()


# ─── Тест 1: инициализация БД ─────────────────────────────────────────────────

class TestDatabaseInit(SmokeBase):
    """init_db() создаёт все критические таблицы."""

    REQUIRED_TABLES = [
        "projects", "chapters", "state_engine",
        "pipeline_runs", "pipeline_iterations",
        "l3_memory", "chapter_analysis",
        "api_keys", "settings",
        "generation_history", "knowledge_base",
    ]

    def test_all_required_tables_exist(self):
        from engine.db_core import get_conn
        with get_conn() as conn:
            tables = {
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        missing = [t for t in self.REQUIRED_TABLES if t not in tables]
        self.assertEqual(
            missing, [],
            f"Таблицы отсутствуют после init_db(): {missing}"
        )


# ─── Тест 2: ключевые роуты живые ────────────────────────────────────────────

class TestCoreRoutesAlive(SmokeBase):
    """Ключевые роуты возвращают не 500."""

    def _assert_not_500(self, method, url, json=None, msg=""):
        if method == "GET":
            r = self.client.get(url)
        else:
            r = self.client.post(url, json=json or {})
        self.assertNotEqual(
            r.status_code, 500,
            f"{method} {url} вернул 500. {msg}"
        )
        return r

    def test_get_models(self):
        r = self._assert_not_500("GET", "/api/models")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIsInstance(data, (list, dict),
                              "/api/models должен вернуть JSON")

    def test_get_engine_status(self):
        r = self._assert_not_500("GET", "/api/engine/status")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        # Движок не найден в тестовой среде → available=False, но роут живой
        self.assertIn("available", data,
                      "/api/engine/status должен содержать 'available'")

    def test_get_chapters_without_project(self):
        """Без активного проекта /api/chapters возвращает пустой список, не ошибку."""
        r = self._assert_not_500("GET", "/api/chapters")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIsInstance(data, list)
        self.assertEqual(data, [])

    def test_get_engine_path(self):
        # /api/engine/path принимает только POST/PUT для установки пути.
        # GET → 405 Method Not Allowed — это ожидаемо, не баг.
        r = self.client.get("/api/engine/path")
        self.assertNotEqual(r.status_code, 500)

    def test_get_engine_modules(self):
        r = self._assert_not_500("GET", "/api/engine/modules")
        self.assertIn(r.status_code, (200, 400))

    def test_prevalidation_setting_get(self):
        r = self._assert_not_500("GET", "/api/settings/prevalidation")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("enabled", data,
                      "/api/settings/prevalidation должен содержать 'enabled'")

    def test_prevalidation_setting_post(self):
        r = self._assert_not_500("POST", "/api/settings/prevalidation",
                                  json={"enabled": True})
        self.assertIn(r.status_code, (200, 400))

    def test_generation_history(self):
        r = self._assert_not_500("GET", "/api/generation/history")
        self.assertIn(r.status_code, (200, 400))


# ─── Тест 3: жизненный цикл проекта через HTTP ───────────────────────────────

class TestProjectLifecycle(SmokeBase):
    """Создание → получение → переключение → удаление через HTTP."""

    def test_create_project(self):
        r = self.client.post("/project/new",
                             data={"name": "Дымовой проект", "genre": "фэнтези"},
                             follow_redirects=False)
        # Flask redirect или 200 — не 500
        self.assertNotEqual(r.status_code, 500)
        # Проект реально создался в БД
        from engine.db_projects import get_projects
        projects = get_projects()
        names = [p["name"] for p in projects]
        self.assertIn("Дымовой проект", names)

    def test_switch_project(self):
        from engine.db_projects import create_project
        pid = create_project("Проект для переключения", "детектив")
        r = self.client.get(f"/project/{pid}/switch", follow_redirects=False)
        self.assertNotEqual(r.status_code, 500)
        # После переключения активный проект = pid
        from engine.db import get_active_project_id
        self.assertEqual(get_active_project_id(), pid)

    def test_delete_project(self):
        from engine.db_projects import create_project, get_project
        pid = create_project("Проект для удаления", "хоррор")
        r = self.client.post(f"/project/{pid}/delete", follow_redirects=False)
        self.assertNotEqual(r.status_code, 500)
        from engine.db_projects import get_project
        self.assertIsNone(get_project(pid))

    def test_chapters_after_project_switch(self):
        """После переключения на проект /api/chapters возвращает его главы."""
        from engine.db_projects import create_project, save_chapter
        pid = create_project("Проект с главой", "романс")
        save_chapter(pid, 1, "Текст первой главы", "Задача")
        self.client.get(f"/project/{pid}/switch")  # переключиться

        r = self.client.get("/api/chapters")
        self.assertEqual(r.status_code, 200)
        chapters = r.get_json()
        self.assertIsInstance(chapters, list)
        self.assertGreaterEqual(len(chapters), 1)


# ─── Тест 4: before_request validation не падает ─────────────────────────────

class TestBeforeRequestValidation(SmokeBase):
    """
    _validate_engine_once() срабатывает при первом запросе и не роняет приложение
    даже если ENGINE_PATH не существует.
    """

    def test_first_request_does_not_raise(self):
        """
        Первый запрос триггерит validate_engine_once.
        Движок не найден → предупреждение в лог, но ответ не 500.
        """
        import web.app as webapp
        webapp._engine_validated = False  # сбрасываем чтобы хук сработал

        r = self.client.get("/api/models")
        self.assertNotEqual(r.status_code, 500)
        # После первого запроса флаг установлен
        self.assertTrue(webapp._engine_validated)

    def test_second_request_skips_validation(self):
        """
        Второй запрос не повторяет валидацию.
        Проверяем через флаг _engine_validated.
        """
        import web.app as webapp
        webapp._engine_validated = True  # уже валидировали

        # Патчим validate_engine_paths чтобы убедиться что не вызывается
        with patch("engine.engine_loaders.validate_engine_paths") as mock_val:
            self.client.get("/api/models")
        mock_val.assert_not_called()


# ─── Запуск без pytest ────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
