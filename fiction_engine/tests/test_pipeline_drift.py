"""
test_pipeline_drift.py — engine/pipeline_drift.py

Покрываем:
  A. _parse_drift_result — парсинг ответа LLM
     1. Полный корректный ответ → score, issues, critical
     2. Нет ОЦЕНКА: → fallback 7.0
     3. КРИТИЧНО: нет → critical=False
     4. КРИТИЧНО: да → critical=True
     5. Нет ПРОБЛЕМЫ: → issues=""
     6. Дробный score (8.5/10) → float

  B. _build_warning — построение предупреждения
     7. score >= 7.5 → None
     8. 6.0 <= score < 7.5 → мягкое предупреждение, нет "❌"
     9. score < 6.0 → строгое предупреждение с ❌/⚠

  C. check_voice_drift — основная функция
    10. Текст < 200 символов → {"checked": False, "reason": "text_too_short"}
    11. Нет эталона → {"checked": False, "reason": "no_reference_available"}
    12. Успешный вызов → checked=True, score, issues, warning в результате
    13. LLM падает → checked=False, не бросает исключение
    14. score ниже 6 → warning непустой
    15. score выше 7.5 → warning None

  D. _get_reference — получение эталона
    16. Нет голосового профиля, нет глав → None
    17. Есть голосовой профиль → (label, text)
    18. Нет профиля, есть ранняя глава >= 300 символов → (label, text)
    19. Нет профиля, глава < 300 символов → None
"""

import pytest
from unittest.mock import patch, MagicMock


class TestParseDriftResult:
    """A. _parse_drift_result."""

    def test_full_correct_response(self):
        from engine.pipeline_drift import _parse_drift_result
        text = "ОЦЕНКА: 8/10\nПРОБЛЕМЫ: нет\nКРИТИЧНО: нет"
        score, issues, critical = _parse_drift_result(text)
        assert score == pytest.approx(8.0)
        assert issues == "нет"
        assert critical is False

    def test_no_score_fallback(self):
        from engine.pipeline_drift import _parse_drift_result
        score, _, _ = _parse_drift_result("ПРОБЛЕМЫ: нет\nКРИТИЧНО: нет")
        assert score == pytest.approx(7.0)

    def test_critical_da(self):
        from engine.pipeline_drift import _parse_drift_result
        _, _, critical = _parse_drift_result("ОЦЕНКА: 4/10\nПРОБЛЕМЫ: нет\nКРИТИЧНО: да")
        assert critical is True

    def test_critical_net(self):
        from engine.pipeline_drift import _parse_drift_result
        _, _, critical = _parse_drift_result("ОЦЕНКА: 9/10\nПРОБЛЕМЫ: нет\nКРИТИЧНО: нет")
        assert critical is False

    def test_no_problems_field(self):
        from engine.pipeline_drift import _parse_drift_result
        _, issues, _ = _parse_drift_result("ОЦЕНКА: 7/10\nКРИТИЧНО: нет")
        assert issues == ""

    def test_fractional_score(self):
        from engine.pipeline_drift import _parse_drift_result
        score, _, _ = _parse_drift_result("ОЦЕНКА: 8.5/10\nПРОБЛЕМЫ: нет\nКРИТИЧНО: нет")
        assert score == pytest.approx(8.5)

    def test_issues_multiword(self):
        from engine.pipeline_drift import _parse_drift_result
        _, issues, _ = _parse_drift_result(
            "ОЦЕНКА: 6/10\nПРОБЛЕМЫ: темп предложений; атрибуция диалогов\nКРИТИЧНО: нет"
        )
        assert "темп" in issues
        assert "атрибуция" in issues

    def test_case_insensitive_critical(self):
        from engine.pipeline_drift import _parse_drift_result
        _, _, critical = _parse_drift_result("ОЦЕНКА: 4/10\nПРОБЛЕМЫ: нет\nКРИТИЧНО: ДА")
        assert critical is True


class TestBuildWarning:
    """B. _build_warning."""

    def test_high_score_returns_none(self):
        from engine.pipeline_drift import _build_warning
        assert _build_warning(8.0, "") is None
        assert _build_warning(7.5, "нет") is None
        assert _build_warning(10.0, "") is None

    def test_medium_score_soft_warning(self):
        from engine.pipeline_drift import _build_warning
        result = _build_warning(7.0, "небольшие отклонения")
        assert result is not None
        assert isinstance(result, str)
        assert "небольшие отклонения" in result

    def test_low_score_strict_warning(self):
        from engine.pipeline_drift import _build_warning
        result = _build_warning(4.5, "темп; атрибуция")
        assert result is not None
        assert "4.5" in result
        assert "темп" in result

    def test_boundary_exactly_6(self):
        """score==6.0 → мягкое (не строгое)."""
        from engine.pipeline_drift import _build_warning
        result = _build_warning(6.0, "проблемы")
        assert result is not None
        # Не строгое: нет "Рекомендуется"
        assert "Рекомендуется" not in result

    def test_boundary_just_below_6(self):
        """score==5.9 → строгое."""
        from engine.pipeline_drift import _build_warning
        result = _build_warning(5.9, "проблемы")
        assert result is not None
        assert "Рекомендуется" in result


class TestCheckVoiceDrift:
    """C. check_voice_drift."""

    def test_short_text_returns_not_checked(self, project_id):
        from engine.pipeline_drift import check_voice_drift
        result = check_voice_drift(project_id, 5, "короткий", "model:v1")
        assert result["checked"] is False
        assert result["reason"] == "text_too_short"

    def test_no_reference_returns_not_checked(self, project_id):
        from engine.pipeline_drift import check_voice_drift
        text = "А" * 300
        with patch("engine.pipeline_drift._get_reference", return_value=None):
            result = check_voice_drift(project_id, 5, text, "model:v1")
        assert result["checked"] is False
        assert result["reason"] == "no_reference_available"

    def test_successful_check(self, project_id):
        from engine.pipeline_drift import check_voice_drift
        text = "А" * 300
        mock_response = "ОЦЕНКА: 8/10\nПРОБЛЕМЫ: нет\nКРИТИЧНО: нет"

        with patch("engine.pipeline_drift._get_reference",
                   return_value=("Голосовой профиль", "эталон текст")), \
             patch("engine.pipeline_drift.save_drift_check"):
            result = check_voice_drift(
                project_id, 5, text, "model:v1",
                call_fn=lambda *a, **kw: mock_response
            )

        assert result["checked"] is True
        assert result["score"] == pytest.approx(8.0)
        assert "issues" in result
        assert "warning" in result
        assert "reference" in result

    def test_llm_exception_returns_not_checked(self, project_id):
        from engine.pipeline_drift import check_voice_drift
        text = "А" * 300

        def failing_call(*a, **kw):
            raise RuntimeError("LLM недоступен")

        with patch("engine.pipeline_drift._get_reference",
                   return_value=("Профиль", "текст")):
            result = check_voice_drift(
                project_id, 5, text, "model:v1", call_fn=failing_call
            )

        assert result["checked"] is False

    def test_low_score_produces_warning(self, project_id):
        from engine.pipeline_drift import check_voice_drift
        text = "А" * 300
        mock_response = "ОЦЕНКА: 4/10\nПРОБЛЕМЫ: темп; диалог\nКРИТИЧНО: нет"

        with patch("engine.pipeline_drift._get_reference",
                   return_value=("Профиль", "эталон")), \
             patch("engine.pipeline_drift.save_drift_check"):
            result = check_voice_drift(
                project_id, 5, text, "model:v1",
                call_fn=lambda *a, **kw: mock_response
            )

        assert result["checked"] is True
        assert result["warning"] is not None

    def test_high_score_no_warning(self, project_id):
        from engine.pipeline_drift import check_voice_drift
        text = "А" * 300
        mock_response = "ОЦЕНКА: 9/10\nПРОБЛЕМЫ: нет\nКРИТИЧНО: нет"

        with patch("engine.pipeline_drift._get_reference",
                   return_value=("Профиль", "эталон")), \
             patch("engine.pipeline_drift.save_drift_check"):
            result = check_voice_drift(
                project_id, 5, text, "model:v1",
                call_fn=lambda *a, **kw: mock_response
            )

        assert result["warning"] is None


class TestGetReference:
    """D. _get_reference."""

    def test_no_voice_no_chapters_returns_none(self, project_id):
        from engine.pipeline_drift import _get_reference
        with patch("engine.pipeline_drift.get_active_voice", return_value=None):
            result = _get_reference(project_id, chapter_num=5)
        assert result is None

    def test_active_voice_returns_label_and_text(self, project_id):
        from engine.pipeline_drift import _get_reference
        mock_voice = {"name": "Тестовый голос", "profile": "Профиль голоса " * 20}
        with patch("engine.pipeline_drift.get_active_voice", return_value=mock_voice):
            result = _get_reference(project_id, chapter_num=5)
        assert result is not None
        label, text = result
        assert "Тестовый голос" in label
        assert len(text) > 0

    def test_no_voice_early_chapter_as_fallback(self, project_id):
        from engine.pipeline_drift import _get_reference
        from engine.db_projects import save_chapter
        # Глава 1 — длинная (>= 300 символов)
        long_text = "Герой шёл по дороге. " * 20
        save_chapter(project_id, 1, long_text, "Начало")

        with patch("engine.pipeline_drift.get_active_voice", return_value=None):
            result = _get_reference(project_id, chapter_num=5)

        assert result is not None
        label, text = result
        assert "1" in label
        assert len(text) > 0

    def test_no_voice_short_chapter_returns_none(self, project_id):
        from engine.pipeline_drift import _get_reference
        from engine.db_projects import save_chapter
        # Глава слишком короткая (< 300 символов)
        save_chapter(project_id, 1, "Короткая глава.", "Начало")

        with patch("engine.pipeline_drift.get_active_voice", return_value=None):
            result = _get_reference(project_id, chapter_num=5)

        assert result is None
