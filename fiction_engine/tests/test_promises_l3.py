"""
test_promises_l3.py — тесты структурированных promises в l3_memory.

Покрывает:
  A. normalize_promises — legacy строка и новый список
  B. get_active_promises — фильтрация закрытых
  C. mark_promise_resolved — обновление саммари в БД
  D. generate_l3_summary — promises сохраняются как список
  E. get_l3_context — закрытые promises не показываются
"""
import json
import pytest
from unittest.mock import patch


# ─── A. normalize_promises ────────────────────────────────────────────────────

class TestNormalizePromises:

    def test_legacy_string_becomes_single_item_list(self):
        from engine.l3_memory import normalize_promises
        result = normalize_promises("Герой узнает правду об отце", chapter_num=5)
        assert len(result) == 1
        assert result[0]["text"] == "Герой узнает правду об отце"
        assert result[0]["id"] == "5_0"
        assert result[0]["resolved"] is False
        assert result[0]["resolved_chapter"] is None

    def test_empty_string_returns_empty_list(self):
        from engine.l3_memory import normalize_promises
        assert normalize_promises("", chapter_num=3) == []

    def test_whitespace_string_returns_empty_list(self):
        from engine.l3_memory import normalize_promises
        assert normalize_promises("   ", chapter_num=3) == []

    def test_none_returns_empty_list(self):
        from engine.l3_memory import normalize_promises
        assert normalize_promises(None, chapter_num=3) == []

    def test_valid_list_passthrough(self):
        from engine.l3_memory import normalize_promises
        raw = [
            {"id": "7_0", "text": "Убийца вернётся", "resolved": False, "resolved_chapter": None},
            {"id": "7_1", "text": "Ключ найдут",     "resolved": True,  "resolved_chapter": 10},
        ]
        result = normalize_promises(raw, chapter_num=7)
        assert len(result) == 2
        assert result[0]["id"] == "7_0"
        assert result[1]["resolved"] is True
        assert result[1]["resolved_chapter"] == 10

    def test_list_with_empty_text_skipped(self):
        from engine.l3_memory import normalize_promises
        raw = [
            {"id": "3_0", "text": "",        "resolved": False},
            {"id": "3_1", "text": "Обещание", "resolved": False},
        ]
        result = normalize_promises(raw, chapter_num=3)
        assert len(result) == 1
        assert result[0]["id"] == "3_1"

    def test_list_item_missing_id_gets_generated(self):
        from engine.l3_memory import normalize_promises
        raw = [{"text": "Обещание без id", "resolved": False}]
        result = normalize_promises(raw, chapter_num=4)
        assert result[0]["id"] == "4_0"

    def test_list_item_missing_resolved_defaults_false(self):
        from engine.l3_memory import normalize_promises
        raw = [{"id": "2_0", "text": "Обещание"}]
        result = normalize_promises(raw, chapter_num=2)
        assert result[0]["resolved"] is False


# ─── B. get_active_promises ───────────────────────────────────────────────────

class TestGetActivePromises:

    def test_returns_only_unresolved(self):
        from engine.l3_memory import get_active_promises
        promises = [
            {"id": "1_0", "text": "Открытое",  "resolved": False},
            {"id": "1_1", "text": "Закрытое",  "resolved": True},
            {"id": "1_2", "text": "Открытое2", "resolved": False},
        ]
        active = get_active_promises(promises)
        assert len(active) == 2
        assert all(not p["resolved"] for p in active)

    def test_all_resolved_returns_empty(self):
        from engine.l3_memory import get_active_promises
        promises = [
            {"id": "5_0", "text": "Закрытое", "resolved": True},
        ]
        assert get_active_promises(promises) == []

    def test_empty_list_returns_empty(self):
        from engine.l3_memory import get_active_promises
        assert get_active_promises([]) == []

    def test_preserves_promise_data(self):
        from engine.l3_memory import get_active_promises
        promises = [{"id": "3_0", "text": "Текст", "resolved": False, "resolved_chapter": None}]
        active = get_active_promises(promises)
        assert active[0]["id"] == "3_0"
        assert active[0]["text"] == "Текст"


# ─── C. mark_promise_resolved ─────────────────────────────────────────────────

class TestMarkPromiseResolved:

    def test_marks_promise_as_resolved(self, project_id):
        from engine.l3_memory import generate_l3_summary, mark_promise_resolved, normalize_promises, get_active_promises
        from engine.db import get_l3_summary

        # Создаём саммари с одним активным обещанием
        raw = json.dumps({
            "events": "событие",
            "characters": "",
            "conflicts": "",
            "promises": [{"id": "1_0", "text": "Герой вернётся", "resolved": False, "resolved_chapter": None}],
            "mood": "нейтральное",
        })
        generate_l3_summary(project_id, 1, "А" * 200, lambda p: raw)

        result = mark_promise_resolved(project_id, "1_0", resolved_chapter=5)
        assert result is True

        saved = get_l3_summary(project_id, 1)
        promises = normalize_promises(saved["promises"], 1)
        assert promises[0]["resolved"] is True
        assert promises[0]["resolved_chapter"] == 5

    def test_returns_false_for_unknown_promise(self, project_id):
        from engine.l3_memory import mark_promise_resolved
        result = mark_promise_resolved(project_id, "99_0", resolved_chapter=5)
        assert result is False

    def test_returns_false_for_invalid_id_format(self, project_id):
        from engine.l3_memory import mark_promise_resolved
        result = mark_promise_resolved(project_id, "invalid", resolved_chapter=5)
        assert result is False

    def test_already_resolved_not_updated_again(self, project_id):
        from engine.l3_memory import generate_l3_summary, mark_promise_resolved, normalize_promises
        from engine.db import get_l3_summary

        raw = json.dumps({
            "events": "событие",
            "characters": "", "conflicts": "", "mood": "",
            "promises": [{"id": "1_0", "text": "Обещание", "resolved": True, "resolved_chapter": 3}],
        })
        generate_l3_summary(project_id, 1, "А" * 200, lambda p: raw)

        result = mark_promise_resolved(project_id, "1_0", resolved_chapter=7)
        # Уже закрытое — возвращаем False (не обновляем)
        assert result is False

        saved = get_l3_summary(project_id, 1)
        promises = normalize_promises(saved["promises"], 1)
        assert promises[0]["resolved_chapter"] == 3  # не перезаписано


# ─── D. generate_l3_summary — promises как список ────────────────────────────

class TestGenerateSummaryPromises:

    def test_structured_promises_saved_as_list(self, project_id):
        from engine.l3_memory import generate_l3_summary, normalize_promises
        raw = json.dumps({
            "events": "событие",
            "characters": "Иван изменился",
            "conflicts": "конфликт",
            "promises": [
                {"id": "2_0", "text": "Убийца вернётся", "resolved": False, "resolved_chapter": None},
                {"id": "2_1", "text": "Ключ спрятан",    "resolved": False, "resolved_chapter": None},
            ],
            "mood": "тревожное",
        })
        result = generate_l3_summary(project_id, 2, "А" * 200, lambda p: raw)
        assert result is not None
        promises = normalize_promises(result["promises"], 2)
        assert len(promises) == 2
        assert promises[0]["id"] == "2_0"
        assert promises[1]["text"] == "Ключ спрятан"

    def test_legacy_string_promises_normalized_on_save(self, project_id):
        from engine.l3_memory import generate_l3_summary, normalize_promises
        raw = json.dumps({
            "events": "событие",
            "characters": "", "conflicts": "",
            "promises": "Герой узнает тайну",
            "mood": "тёмное",
        })
        result = generate_l3_summary(project_id, 1, "А" * 200, lambda p: raw)
        assert result is not None
        promises = normalize_promises(result["promises"], 1)
        assert len(promises) == 1
        assert promises[0]["text"] == "Герой узнает тайну"
        assert promises[0]["resolved"] is False

    def test_empty_promises_saved_as_empty_list(self, project_id):
        from engine.l3_memory import generate_l3_summary, normalize_promises
        raw = json.dumps({
            "events": "событие",
            "characters": "", "conflicts": "",
            "promises": [],
            "mood": "нейтральное",
        })
        result = generate_l3_summary(project_id, 1, "А" * 200, lambda p: raw)
        assert result is not None
        promises = normalize_promises(result["promises"], 1)
        assert promises == []


# ─── E. get_l3_context — только активные promises ────────────────────────────

class TestGetL3ContextPromises:

    def test_active_promises_shown(self, project_id):
        from engine.l3_memory import get_l3_context
        fake = [{
            "chapter_num": 1,
            "events": "событие",
            "characters": "",
            "conflicts": "",
            "promises": [{"id": "1_0", "text": "Убийца вернётся", "resolved": False}],
            "mood": "",
        }]
        with patch("engine.l3_memory.get_l3_summaries", return_value=fake):
            result = get_l3_context(project_id, before_chapter=2)
        assert "Убийца вернётся" in result

    def test_resolved_promises_not_shown(self, project_id):
        from engine.l3_memory import get_l3_context
        fake = [{
            "chapter_num": 1,
            "events": "событие",
            "characters": "",
            "conflicts": "",
            "promises": [{"id": "1_0", "text": "Убийца вернётся", "resolved": True, "resolved_chapter": 3}],
            "mood": "",
        }]
        with patch("engine.l3_memory.get_l3_summaries", return_value=fake):
            result = get_l3_context(project_id, before_chapter=5)
        assert "Убийца вернётся" not in result

    def test_mixed_promises_shows_only_active(self, project_id):
        from engine.l3_memory import get_l3_context
        fake = [{
            "chapter_num": 3,
            "events": "событие",
            "characters": "", "conflicts": "",
            "promises": [
                {"id": "3_0", "text": "Активное обещание", "resolved": False},
                {"id": "3_1", "text": "Закрытое обещание", "resolved": True, "resolved_chapter": 4},
            ],
            "mood": "",
        }]
        with patch("engine.l3_memory.get_l3_summaries", return_value=fake):
            result = get_l3_context(project_id, before_chapter=6)
        assert "Активное обещание" in result
        assert "Закрытое обещание" not in result
