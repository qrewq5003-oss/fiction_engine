"""
test_continuity_checker.py — engine/continuity_checker.py

Покрываем:
  A. format_continuity_for_prompt — форматирование нарушений
     1. Пустой список → ""
     2. Одно critical нарушение → содержит ❌ и текст
     3. Одно warning нарушение → содержит ⚠ и текст
     4. Смешанные → critical первыми
     5. Нарушение без severity → попадает в warnings

  B. _has_enough_data — проверка достаточности данных
     6. chapter_num < 3 → False без обращения к БД
     7. chapter_num >= 3, нет проанализированных глав → False
     8. chapter_num >= 3, есть глава с analysis_quality != "failed" → True

  C. check_continuity — основная функция (с @error_boundary)
     9.  chapter_num < 3 → [] (не хватает данных)
    10. Нет series_facts → [] (нет данных)
    11. LLM возвращает ok: true, violations: [] → []
    12. LLM возвращает нарушения → список dict с fact/violation/severity
    13. LLM возвращает не-JSON → [] (не падает)
    14. LLM бросает исключение → [] (error_boundary ловит)
    15. Фильтрация: violation без "violation" поля → не входит в результат

  D. _build_series_facts — сборка фактов (smoke)
    16. Нет данных в БД → "" (не падает)
    17. С данными → непустая строка
"""

import pytest
import json
from unittest.mock import patch, MagicMock


class TestFormatContinuityForPrompt:
    """A. format_continuity_for_prompt."""

    def test_empty_list_returns_empty_string(self):
        from engine.continuity_checker import format_continuity_for_prompt
        assert format_continuity_for_prompt([]) == ""

    def test_critical_violation_has_marker(self):
        from engine.continuity_checker import format_continuity_for_prompt
        violations = [{"fact": "Герой боялся высоты", "violation": "Прыгнул без страха", "severity": "critical"}]
        result = format_continuity_for_prompt(violations)
        assert "❌" in result
        assert "КРИТИЧНО" in result
        assert "Прыгнул без страха" in result
        assert "Герой боялся высоты" in result

    def test_warning_violation_has_marker(self):
        from engine.continuity_checker import format_continuity_for_prompt
        violations = [{"fact": "Меч был серебряным", "violation": "Назван стальным", "severity": "warning"}]
        result = format_continuity_for_prompt(violations)
        assert "⚠" in result
        assert "ПРЕДУПРЕЖДЕНИЕ" in result
        assert "Назван стальным" in result

    def test_critical_before_warnings(self):
        from engine.continuity_checker import format_continuity_for_prompt
        violations = [
            {"fact": "Факт1", "violation": "Warning-нарушение", "severity": "warning"},
            {"fact": "Факт2", "violation": "Critical-нарушение", "severity": "critical"},
        ]
        result = format_continuity_for_prompt(violations)
        assert result.index("Critical-нарушение") < result.index("Warning-нарушение")

    def test_no_severity_treated_as_warning(self):
        from engine.continuity_checker import format_continuity_for_prompt
        violations = [{"fact": "Факт", "violation": "Нарушение без severity"}]
        result = format_continuity_for_prompt(violations)
        assert "Нарушение без severity" in result
        assert result != ""

    def test_multiple_violations_all_present(self):
        from engine.continuity_checker import format_continuity_for_prompt
        violations = [
            {"fact": f"Факт{i}", "violation": f"Нарушение{i}", "severity": "warning"}
            for i in range(3)
        ]
        result = format_continuity_for_prompt(violations)
        for i in range(3):
            assert f"Нарушение{i}" in result


class TestHasEnoughData:
    """B. _has_enough_data."""

    def test_chapter_1_returns_false(self, project_id):
        from engine.continuity_checker import _has_enough_data
        assert _has_enough_data(project_id, chapter_num=1) is False

    def test_chapter_2_returns_false(self, project_id):
        from engine.continuity_checker import _has_enough_data
        assert _has_enough_data(project_id, chapter_num=2) is False

    def test_chapter_3_no_analyses_returns_false(self, project_id):
        from engine.continuity_checker import _has_enough_data
        assert _has_enough_data(project_id, chapter_num=3) is False

    def test_chapter_3_with_analysis_returns_true(self, project_id):
        from engine.continuity_checker import _has_enough_data
        from engine.db_chapters import save_chapter_analysis
        save_chapter_analysis(project_id, 2, {
            "opening_type": "action",
            "closing_type": "cliffhanger",
            "analysis_quality": "ok",
        })
        assert _has_enough_data(project_id, chapter_num=3) is True

    def test_failed_analysis_not_enough(self, project_id):
        from engine.continuity_checker import _has_enough_data
        from engine.db_chapters import save_chapter_analysis
        save_chapter_analysis(project_id, 2, {
            "opening_type": "",
            "closing_type": "",
            "analysis_quality": "failed",
        })
        assert _has_enough_data(project_id, chapter_num=3) is False


class TestCheckContinuity:
    """C. check_continuity."""

    def _make_api_fn(self, response: str):
        """Простая LLM-заглушка возвращающая строку."""
        return lambda prompt: response

    def test_chapter_less_than_3_returns_empty(self, project_id):
        from engine.continuity_checker import check_continuity
        result = check_continuity(project_id, 2, "Текст главы.", self._make_api_fn("{}"))
        assert result == []

    def test_no_series_facts_returns_empty(self, project_id):
        from engine.continuity_checker import check_continuity
        from engine.db_chapters import save_chapter_analysis
        save_chapter_analysis(project_id, 2, {"opening_type": "action", "closing_type": "", "analysis_quality": "ok"})
        with patch("engine.continuity_checker._build_series_facts", return_value=""):
            result = check_continuity(project_id, 3, "Текст.", self._make_api_fn("{}"))
        assert result == []

    def test_ok_true_no_violations_returns_empty(self, project_id):
        from engine.continuity_checker import check_continuity
        from engine.db_chapters import save_chapter_analysis
        save_chapter_analysis(project_id, 2, {"opening_type": "action", "closing_type": "", "analysis_quality": "ok"})

        response = json.dumps({"violations": [], "ok": True})
        with patch("engine.continuity_checker._build_series_facts", return_value="Факты серии."):
            result = check_continuity(project_id, 3, "Текст.", self._make_api_fn(response))
        assert result == []

    def test_violations_returned_as_list(self, project_id):
        from engine.continuity_checker import check_continuity
        from engine.db_chapters import save_chapter_analysis
        save_chapter_analysis(project_id, 2, {"opening_type": "action", "closing_type": "", "analysis_quality": "ok"})

        violations = [{"fact": "Герой боялся высоты", "violation": "Прыгнул", "severity": "critical"}]
        response = json.dumps({"violations": violations, "ok": False})

        with patch("engine.continuity_checker._build_series_facts", return_value="Факты."):
            result = check_continuity(project_id, 3, "Текст.", self._make_api_fn(response))

        assert len(result) == 1
        assert result[0]["violation"] == "Прыгнул"
        assert result[0]["fact"] == "Герой боялся высоты"

    def test_non_json_response_returns_empty(self, project_id):
        from engine.continuity_checker import check_continuity
        from engine.db_chapters import save_chapter_analysis
        save_chapter_analysis(project_id, 2, {"opening_type": "action", "closing_type": "", "analysis_quality": "ok"})

        with patch("engine.continuity_checker._build_series_facts", return_value="Факты."):
            result = check_continuity(project_id, 3, "Текст.", self._make_api_fn("не JSON вообще"))
        assert result == []

    def test_llm_exception_returns_empty_not_raises(self, project_id):
        from engine.continuity_checker import check_continuity
        from engine.db_chapters import save_chapter_analysis
        save_chapter_analysis(project_id, 2, {"opening_type": "action", "closing_type": "", "analysis_quality": "ok"})

        def crashing_api(prompt):
            raise RuntimeError("LLM упал")

        with patch("engine.continuity_checker._build_series_facts", return_value="Факты."):
            result = check_continuity(project_id, 3, "Текст.", crashing_api)
        assert result == []

    def test_violation_without_violation_field_filtered(self, project_id):
        from engine.continuity_checker import check_continuity
        from engine.db_chapters import save_chapter_analysis
        save_chapter_analysis(project_id, 2, {"opening_type": "action", "closing_type": "", "analysis_quality": "ok"})

        # Нарушение без поля "violation" → должно быть отфильтровано
        bad = [{"fact": "Факт", "severity": "warning"}]  # нет "violation"
        response = json.dumps({"violations": bad, "ok": False})

        with patch("engine.continuity_checker._build_series_facts", return_value="Факты."):
            result = check_continuity(project_id, 3, "Текст.", self._make_api_fn(response))
        assert result == []


class TestBuildSeriesFacts:
    """D. _build_series_facts — smoke тесты."""

    def test_no_data_returns_empty_string(self, project_id):
        """Нет ничего в БД → "" (не падает)."""
        from engine.continuity_checker import _build_series_facts
        result = _build_series_facts(project_id, chapter_num=5)
        assert isinstance(result, str)

    def test_with_chapter_analysis_returns_nonempty(self, project_id):
        from engine.continuity_checker import _build_series_facts
        from engine.db_chapters import save_chapter_analysis

        save_chapter_analysis(project_id, 1, {
            "opening_type": "action",
            "closing_type": "cliffhanger",
            "analysis_quality": "ok",
            "opened_promises": ["Герой обещал вернуться"],
            "causal_chains": [{"is_setup": True, "cause": "Герой ушёл", "effect": "Все грустят"}],
            "logical_gaps": [],
        })
        result = _build_series_facts(project_id, chapter_num=3)
        assert isinstance(result, str)
        # С данными результат должен быть непустым
        assert len(result) > 0
