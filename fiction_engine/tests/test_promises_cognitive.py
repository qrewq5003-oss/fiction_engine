"""
test_promises_cognitive.py — тесты promises в cognitive_memory.

Покрывает:
  A. score_summary — список promises учитывает только активные
  B. get_weighted_promises — фильтрует закрытые, возвращает id в строке
  C. _format_cognitive_context — закрытые promises не попадают в контекст
"""
import pytest
from unittest.mock import patch, MagicMock


def _make_summary(chapter_num: int, promises=None, **kwargs) -> dict:
    return {
        "chapter_num": chapter_num,
        "promises":    promises if promises is not None else [],
        "conflicts":   kwargs.get("conflicts", ""),
        "characters":  kwargs.get("characters", ""),
        "events":      kwargs.get("events", ""),
        "mood":        kwargs.get("mood", ""),
    }


# ─── A. score_summary — promises как список ──────────────────────────────────

class TestScoreSummaryWithStructuredPromises:

    def test_active_promise_list_gets_score(self):
        from engine.cognitive_memory import score_summary
        summary = _make_summary(5, promises=[
            {"id": "5_0", "text": "Обещание", "resolved": False}
        ])
        scores = score_summary(summary, distance=1)
        assert "promises" in scores
        assert scores["promises"] > 0

    def test_all_resolved_promises_no_score(self):
        from engine.cognitive_memory import score_summary
        summary = _make_summary(5, promises=[
            {"id": "5_0", "text": "Закрытое", "resolved": True, "resolved_chapter": 7}
        ])
        scores = score_summary(summary, distance=1)
        assert "promises" not in scores

    def test_empty_promises_list_no_score(self):
        from engine.cognitive_memory import score_summary
        summary = _make_summary(5, promises=[])
        scores = score_summary(summary, distance=1)
        assert "promises" not in scores

    def test_legacy_string_promise_gets_score(self):
        """Legacy строка должна по-прежнему давать вес (normalize_promises её обработает)."""
        from engine.cognitive_memory import score_summary
        summary = _make_summary(3, promises="Герой вернётся")
        scores = score_summary(summary, distance=2)
        assert "promises" in scores

    def test_mixed_active_and_resolved_gets_score(self):
        """Если есть хотя бы одно активное — вес есть."""
        from engine.cognitive_memory import score_summary
        summary = _make_summary(5, promises=[
            {"id": "5_0", "text": "Закрытое",  "resolved": True},
            {"id": "5_1", "text": "Активное",  "resolved": False},
        ])
        scores = score_summary(summary, distance=1)
        assert "promises" in scores


# ─── B. get_weighted_promises ─────────────────────────────────────────────────

class TestGetWeightedPromisesStructured:

    def test_returns_only_active_promises(self):
        from engine.cognitive_memory import get_weighted_promises
        summaries = [
            _make_summary(1, promises=[
                {"id": "1_0", "text": "Активное",  "resolved": False},
                {"id": "1_1", "text": "Закрытое",  "resolved": True, "resolved_chapter": 3},
            ]),
        ]
        with patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
            result = get_weighted_promises(project_id=1, before_chapter=5)
        assert "Активное" in result
        assert "Закрытое" not in result

    def test_promise_id_shown_in_output(self):
        """id должен быть виден в строке — используется для resolved_promises в анализе."""
        from engine.cognitive_memory import get_weighted_promises
        summaries = [
            _make_summary(3, promises=[
                {"id": "3_0", "text": "Убийца вернётся", "resolved": False},
            ]),
        ]
        with patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
            result = get_weighted_promises(project_id=1, before_chapter=5)
        assert "3_0" in result
        assert "Убийца вернётся" in result

    def test_all_resolved_returns_empty_string(self):
        from engine.cognitive_memory import get_weighted_promises
        summaries = [
            _make_summary(2, promises=[
                {"id": "2_0", "text": "Закрытое", "resolved": True, "resolved_chapter": 4},
            ]),
        ]
        with patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
            result = get_weighted_promises(project_id=1, before_chapter=5)
        assert result == ""

    def test_legacy_string_promises_included(self):
        """Старые саммари со строкой promises тоже показываются."""
        from engine.cognitive_memory import get_weighted_promises
        summaries = [_make_summary(1, promises="Старое обещание")]
        with patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
            result = get_weighted_promises(project_id=1, before_chapter=3)
        assert "Старое обещание" in result

    def test_no_summaries_returns_empty(self):
        from engine.cognitive_memory import get_weighted_promises
        with patch("engine.cognitive_memory.get_l3_summaries", return_value=[]):
            result = get_weighted_promises(project_id=1, before_chapter=5)
        assert result == ""

    def test_multiple_chapters_all_active_included(self):
        from engine.cognitive_memory import get_weighted_promises
        summaries = [
            _make_summary(1, promises=[{"id": "1_0", "text": "Обещание 1", "resolved": False}]),
            _make_summary(3, promises=[{"id": "3_0", "text": "Обещание 3", "resolved": False}]),
        ]
        with patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
            result = get_weighted_promises(project_id=1, before_chapter=5)
        assert "Обещание 1" in result
        assert "Обещание 3" in result


# ─── C. cognitive context — закрытые promises не попадают ────────────────────

class TestCognitiveContextPromises:

    def test_active_promises_in_context(self):
        from engine.cognitive_memory import get_cognitive_context
        summaries = [
            _make_summary(1, promises=[
                {"id": "1_0", "text": "Активное обещание", "resolved": False},
            ]),
        ]
        with patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
            result = get_cognitive_context(project_id=1, before_chapter=3)
        assert "Активное обещание" in result

    def test_resolved_promises_excluded_from_context(self):
        from engine.cognitive_memory import get_cognitive_context
        summaries = [
            _make_summary(1, promises=[
                {"id": "1_0", "text": "Закрытое обещание", "resolved": True, "resolved_chapter": 2},
            ]),
        ]
        with patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
            result = get_cognitive_context(project_id=1, before_chapter=5)
        assert "Закрытое обещание" not in result

    def test_chapter_without_active_promises_still_included_for_other_fields(self):
        """Глава с только закрытыми promises но с events всё равно попадает в контекст."""
        from engine.cognitive_memory import get_cognitive_context
        summaries = [
            _make_summary(
                2,
                promises=[{"id": "2_0", "text": "Закрытое", "resolved": True}],
                events="важное событие"
            ),
            _make_summary(3, events="событие 3"),
        ]
        with patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
            result = get_cognitive_context(project_id=1, before_chapter=5)
        assert "важное событие" in result
        assert "Закрытое" not in result
