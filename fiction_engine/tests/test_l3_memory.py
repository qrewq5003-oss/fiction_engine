"""test_l3_memory.py — generate_l3_summary, get_l3_context, has_l3_summary, batch_generate_l3"""
import json
import pytest
from unittest.mock import patch


def _ok_response(chapter_num: int = 1):
    """Ответ модели с структурированными promises (новый формат)."""
    return json.dumps({
        "events":     "герой встретил дракона",
        "characters": "Иван испугался",
        "conflicts":  "дракон требует выкуп",
        "promises": [
            {"id": f"{chapter_num}_0", "text": "герой вернётся за мечом",
             "resolved": False, "resolved_chapter": None}
        ],
        "mood": "тревожное",
    })


class TestGenerateL3Summary:
    def test_returns_dict_with_all_fields(self, project_id):
        from engine.l3_memory import generate_l3_summary
        r = generate_l3_summary(project_id, 1, "А" * 200, lambda p: _ok_response(1))
        assert isinstance(r, dict)
        for k in ("events", "characters", "conflicts", "promises", "mood"):
            assert k in r

    def test_promises_saved_as_list(self, project_id):
        """После нормализации promises должен быть list, не str."""
        from engine.l3_memory import generate_l3_summary
        r = generate_l3_summary(project_id, 1, "А" * 200, lambda p: _ok_response(1))
        assert isinstance(r["promises"], list), (
            f"promises должен быть list, получили {type(r['promises'])}"
        )

    def test_legacy_string_promises_normalized_to_list(self, project_id):
        """Legacy строка нормализуется в список при сохранении."""
        from engine.l3_memory import generate_l3_summary
        legacy = json.dumps({
            "events": "событие", "characters": "", "conflicts": "",
            "promises": "герой вернётся",  # старый формат
            "mood": "нейтральное",
        })
        r = generate_l3_summary(project_id, 1, "А" * 200, lambda p: legacy)
        assert isinstance(r["promises"], list)
        assert len(r["promises"]) == 1
        assert r["promises"][0]["text"] == "герой вернётся"

    def test_saves_to_db(self, project_id):
        from engine.l3_memory import generate_l3_summary, has_l3_summary
        generate_l3_summary(project_id, 1, "А" * 200, lambda p: _ok_response(1))
        assert has_l3_summary(project_id, 1) is True

    def test_short_text_returns_none(self, project_id):
        from engine.l3_memory import generate_l3_summary
        assert generate_l3_summary(project_id, 1, "мало", lambda p: _ok_response(1)) is None

    def test_empty_text_returns_none(self, project_id):
        from engine.l3_memory import generate_l3_summary
        assert generate_l3_summary(project_id, 1, "", lambda p: _ok_response(1)) is None

    def test_non_json_response_returns_none(self, project_id):
        from engine.l3_memory import generate_l3_summary
        assert generate_l3_summary(project_id, 1, "А" * 200, lambda p: "не JSON") is None

    def test_exception_in_api_fn_returns_none(self, project_id):
        from engine.l3_memory import generate_l3_summary
        def crash(p): raise RuntimeError("LLM упал")
        assert generate_l3_summary(project_id, 1, "А" * 200, crash) is None

    def test_missing_fields_filled_empty(self, project_id):
        from engine.l3_memory import generate_l3_summary
        r = generate_l3_summary(project_id, 1, "А" * 200,
                                lambda p: json.dumps({"events": "событие"}))
        if r:
            for k in ("events", "characters", "conflicts", "promises", "mood"):
                assert k in r
            assert isinstance(r["promises"], list)


class TestGetL3Context:
    def test_empty_when_no_summaries(self, project_id):
        from engine.l3_memory import get_l3_context
        assert get_l3_context(project_id, before_chapter=10) == ""

    def test_returns_header_and_content(self, project_id):
        from engine.l3_memory import get_l3_context
        fake = [{"chapter_num": 1, "events": "Битва", "characters": "Иван ранен",
                 "conflicts": "", "mood": "мрачное",
                 "promises": [{"id": "1_0", "text": "вернётся", "resolved": False}]}]
        with patch("engine.l3_memory.get_l3_summaries", return_value=fake):
            r = get_l3_context(project_id, before_chapter=2)
        assert "ПАМЯТЬ СЕРИИ" in r
        assert "Битва" in r
        assert "Иван ранен" in r

    def test_active_promise_text_shown(self, project_id):
        """Текст активного обещания должен быть виден в выводе."""
        from engine.l3_memory import get_l3_context
        fake = [{"chapter_num": 1, "events": "событие", "characters": "",
                 "conflicts": "", "mood": "",
                 "promises": [{"id": "1_0", "text": "убийца раскроется", "resolved": False}]}]
        with patch("engine.l3_memory.get_l3_summaries", return_value=fake):
            r = get_l3_context(project_id, before_chapter=2)
        assert "убийца раскроется" in r, "текст активного promise должен быть в контексте"

    def test_resolved_promise_text_not_shown(self, project_id):
        """Текст закрытого обещания не должен попасть в вывод."""
        from engine.l3_memory import get_l3_context
        fake = [{"chapter_num": 1, "events": "событие", "characters": "",
                 "conflicts": "", "mood": "",
                 "promises": [{"id": "1_0", "text": "закрытое обещание",
                               "resolved": True, "resolved_chapter": 3}]}]
        with patch("engine.l3_memory.get_l3_summaries", return_value=fake):
            r = get_l3_context(project_id, before_chapter=5)
        assert "закрытое обещание" not in r

    def test_legacy_string_promise_shown(self, project_id):
        """Legacy строка в promises тоже должна отображаться (normalize_promises)."""
        from engine.l3_memory import get_l3_context
        fake = [{"chapter_num": 2, "events": "событие", "characters": "",
                 "conflicts": "", "mood": "",
                 "promises": "legacy обещание строкой"}]
        with patch("engine.l3_memory.get_l3_summaries", return_value=fake):
            r = get_l3_context(project_id, before_chapter=3)
        assert "legacy обещание строкой" in r

    def test_chapter_number_in_output(self, project_id):
        from engine.l3_memory import get_l3_context
        fake = [{"chapter_num": 7, "events": "событие", "characters": "",
                 "conflicts": "", "promises": [], "mood": ""}]
        with patch("engine.l3_memory.get_l3_summaries", return_value=fake):
            r = get_l3_context(project_id, before_chapter=8)
        assert "7" in r


class TestHasL3Summary:
    def test_false_initially(self, project_id):
        from engine.l3_memory import has_l3_summary
        assert has_l3_summary(project_id, 99) is False

    def test_true_after_save(self, project_id):
        from engine.l3_memory import generate_l3_summary, has_l3_summary
        generate_l3_summary(project_id, 5, "А" * 200, lambda p: _ok_response(5))
        assert has_l3_summary(project_id, 5) is True


class TestBatchGenerateL3:
    def test_returns_three_key_dict(self, project_id):
        from engine.l3_memory import batch_generate_l3
        r = batch_generate_l3(project_id, api_call_fn=lambda p: "{}")
        assert all(k in r for k in ("generated", "skipped", "failed"))

    def test_empty_project_all_empty(self, project_id):
        from engine.l3_memory import batch_generate_l3
        r = batch_generate_l3(project_id, api_call_fn=lambda p: "{}")
        assert r["generated"] == [] and r["failed"] == []

    def test_generates_for_chapter(self, project_id):
        from engine.l3_memory import batch_generate_l3
        from engine.db_projects import save_chapter
        save_chapter(project_id, 1, "Слово. " * 30, "Начало")
        r = batch_generate_l3(project_id, api_call_fn=lambda p: _ok_response(1))
        assert 1 in r["generated"] or 1 in r["failed"]

    def test_skips_existing_summary(self, project_id):
        from engine.l3_memory import batch_generate_l3, generate_l3_summary
        from engine.db_projects import save_chapter
        text = "Слово. " * 30
        save_chapter(project_id, 1, text, "Начало")
        generate_l3_summary(project_id, 1, text, lambda p: _ok_response(1))
        r = batch_generate_l3(project_id, api_call_fn=lambda p: _ok_response(1))
        assert 1 in r["skipped"] and 1 not in r["generated"]

    def test_progress_callback_called(self, project_id):
        from engine.l3_memory import batch_generate_l3
        from engine.db_projects import save_chapter
        save_chapter(project_id, 1, "Слово. " * 30, "Начало")
        calls = []
        batch_generate_l3(project_id, api_call_fn=lambda p: _ok_response(1),
                          progress_callback=lambda cur, tot, ch: calls.append(ch))
        assert len(calls) >= 1
