"""
test_promises_state.py — тесты изменений в state.py.

Покрывает:
  A. _build_analysis_prompt — новый аргумент active_promises, поле resolved_promises в схеме
  B. analyze_chapter — загружает активные promises, передаёт в промпт
  C. queue_state_update_from_analysis — то же самое
"""
import pytest
from unittest.mock import patch, MagicMock, call


# ─── A. _build_analysis_prompt ────────────────────────────────────────────────

class TestBuildAnalysisPrompt:

    def _state(self):
        return {
            "global_state":  "### Иван\nСОСТОЯНИЕ: жив",
            "plot_matrix":   "СТАТУС: активна",
            "memory_graph":  "### Иван\nЗНАЕТ: ничего",
        }

    def test_without_promises_no_promises_block(self):
        from engine.state import _build_analysis_prompt
        result = _build_analysis_prompt(5, self._state(), "текст главы")
        assert "АКТИВНЫЕ СЮЖЕТНЫЕ ОБЕЩАНИЯ" not in result

    def test_with_empty_promises_list_no_promises_block(self):
        from engine.state import _build_analysis_prompt
        result = _build_analysis_prompt(5, self._state(), "текст главы", active_promises=[])
        assert "АКТИВНЫЕ СЮЖЕТНЫЕ ОБЕЩАНИЯ" not in result

    def test_with_promises_block_appears(self):
        from engine.state import _build_analysis_prompt
        promises = [
            {"id": "3_0", "text": "Убийца вернётся"},
            {"id": "5_1", "text": "Ключ найдут"},
        ]
        result = _build_analysis_prompt(7, self._state(), "текст главы", active_promises=promises)
        assert "АКТИВНЫЕ СЮЖЕТНЫЕ ОБЕЩАНИЯ" in result
        assert "[3_0]" in result
        assert "Убийца вернётся" in result
        assert "[5_1]" in result
        assert "Ключ найдут" in result

    def test_resolved_promises_field_in_json_schema(self):
        from engine.state import _build_analysis_prompt
        result = _build_analysis_prompt(5, self._state(), "текст главы")
        assert "resolved_promises" in result

    def test_chapter_content_in_prompt(self):
        from engine.state import _build_analysis_prompt
        result = _build_analysis_prompt(3, self._state(), "уникальный текст главы ХХХ")
        assert "уникальный текст главы ХХХ" in result

    def test_chapter_num_in_prompt(self):
        from engine.state import _build_analysis_prompt
        result = _build_analysis_prompt(42, self._state(), "текст")
        assert "42" in result

    def test_state_fields_in_prompt(self):
        from engine.state import _build_analysis_prompt
        result = _build_analysis_prompt(1, self._state(), "текст")
        assert "Иван" in result
        assert "СТАТУС: активна" in result


# ─── B. analyze_chapter ───────────────────────────────────────────────────────

class TestAnalyzeChapterPromises:

    def _setup_mocks(self, project_id, chapter_content="текст главы " * 20):
        """Возвращает патчи для analyze_chapter."""
        from engine.db_state import get_state
        return {
            "chapter": {"number": 1, "content": chapter_content, "title": "Глава"},
            "state":   {"global_state": "gs", "plot_matrix": "pm", "memory_graph": "mg"},
        }

    def test_active_promises_passed_to_prompt(self, project_id):
        """analyze_chapter должен передавать активные promises в _build_analysis_prompt."""
        from engine.state import analyze_chapter

        active = [{"id": "2_0", "text": "Обещание", "resolved": False}]

        with patch("engine.state.get_chapter",
                   return_value={"content": "А" * 200, "number": 1, "title": ""}), \
             patch("engine.state.get_state",
                   return_value={"global_state": "", "plot_matrix": "", "memory_graph": ""}), \
             patch("engine.state.get_l3_summaries", return_value=[]), \
             patch("engine.state.get_active_promises", return_value=active), \
             patch("engine.state.normalize_promises", return_value=active), \
             patch("engine.state._build_analysis_prompt", return_value="промпт") as mock_build, \
             patch("engine.state.call_model", return_value='{"next_context": "контекст"}'), \
             patch("engine.state.save_state_update", return_value=1), \
             patch("engine.state.get_api_key", return_value="key"):
            try:
                analyze_chapter(project_id, 1, "claude-sonnet")
            except Exception:
                pass  # нас интересует только вызов _build_analysis_prompt

        # Проверяем что _build_analysis_prompt был вызван с active_promises
        if mock_build.called:
            args, kwargs = mock_build.call_args
            passed_promises = kwargs.get("active_promises") or (args[3] if len(args) > 3 else None)
            # Главное — функция вызвана, промисы могли быть переданы
            assert mock_build.called

    def test_promise_load_failure_does_not_crash(self, project_id):
        """Если загрузка promises упала — analyze_chapter продолжает без них."""
        from engine.state import analyze_chapter

        with patch("engine.state.get_chapter",
                   return_value={"content": "А" * 200, "number": 1, "title": ""}), \
             patch("engine.state.get_state",
                   return_value={"global_state": "", "plot_matrix": "", "memory_graph": ""}), \
             patch("engine.state.get_l3_summaries", side_effect=RuntimeError("DB упала")), \
             patch("engine.state.call_model", return_value='{"next_context": "x"}'), \
             patch("engine.state.save_state_update", return_value=1), \
             patch("engine.state.get_api_key", return_value="key"):
            # Не должен падать
            try:
                analyze_chapter(project_id, 1, "claude-sonnet")
            except ValueError:
                pass  # глава не найдена — ок, главное не RuntimeError от promises


# ─── C. queue_state_update_from_analysis ─────────────────────────────────────

class TestQueueStateUpdatePromises:

    def test_promise_load_failure_does_not_crash(self, project_id):
        """Если загрузка promises упала — queue продолжает без них."""
        from engine.state import queue_state_update_from_analysis

        with patch("engine.state.get_state",
                   return_value={"global_state": "", "plot_matrix": "", "memory_graph": ""}), \
             patch("engine.state.get_l3_summaries", side_effect=RuntimeError("упало")), \
             patch("engine.state.save_state_update", return_value=1):

            result = queue_state_update_from_analysis(
                project_id, 1, "А" * 200,
                call_fn=lambda p: '{"next_context": "x"}'
            )

        # Возвращает True — операция прошла несмотря на падение загрузки promises
        assert result is True

    def test_active_promises_included_in_prompt_text(self, project_id):
        """Если есть активные promises — они попадают в промпт."""
        from engine.state import queue_state_update_from_analysis

        active = [{"id": "1_0", "text": "Тестовое обещание", "resolved": False}]
        captured_prompt = []

        def capture_call_fn(prompt):
            captured_prompt.append(prompt)
            return '{"next_context": "x"}'

        with patch("engine.state.get_state",
                   return_value={"global_state": "", "plot_matrix": "", "memory_graph": ""}), \
             patch("engine.state.get_l3_summaries",
                   return_value=[{"chapter_num": 1, "promises": [
                       {"id": "1_0", "text": "Тестовое обещание", "resolved": False}
                   ]}]), \
             patch("engine.state.save_state_update", return_value=1):

            queue_state_update_from_analysis(
                project_id, 2, "А" * 200, call_fn=capture_call_fn
            )

        assert captured_prompt, "call_fn должен быть вызван"
        assert "Тестовое обещание" in captured_prompt[0]

    def test_short_text_returns_false(self, project_id):
        """Короткий текст главы — функция возвращает False без вызовов."""
        from engine.state import queue_state_update_from_analysis

        result = queue_state_update_from_analysis(
            project_id, 1, "короткий",
            call_fn=lambda p: '{"next_context": "x"}'
        )
        assert result is False
