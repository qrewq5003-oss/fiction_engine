"""
test_state_prompts.py — engine/state_prompts.py

A. _trunc
B. strip_empty_placeholders
C. _build_char_prefill / _prefill_from_structured / _prefill_from_freeform
D. build_prompt smoke
"""
import pytest
from unittest.mock import patch


class TestTrunc:
    def test_short_unchanged(self):
        from engine.state_prompts import _trunc
        assert _trunc("короткий", 100) == "короткий"

    def test_long_truncated(self):
        from engine.state_prompts import _trunc
        result = _trunc("слово " * 100, 50)
        assert len(result) <= 50

    def test_empty(self):
        from engine.state_prompts import _trunc
        assert _trunc("", 100) == ""

    def test_exact_limit(self):
        from engine.state_prompts import _trunc
        t = "ровно"
        assert _trunc(t, len(t)) == t


class TestStripEmptyPlaceholders:
    def test_removes_empty_brackets(self):
        from engine.state_prompts import strip_empty_placeholders
        result = strip_empty_placeholders("Контент\n[]\nЕщё")
        assert "[]" not in result
        assert "Контент" in result

    def test_preserves_filled_brackets(self):
        from engine.state_prompts import strip_empty_placeholders
        text = "Данные [значение] здесь"
        assert "[значение]" in strip_empty_placeholders(text)

    def test_empty_string(self):
        from engine.state_prompts import strip_empty_placeholders
        assert strip_empty_placeholders("") == ""

    def test_valid_content_unchanged(self):
        from engine.state_prompts import strip_empty_placeholders
        text = "Иван: устал\nМария: ждёт"
        result = strip_empty_placeholders(text)
        assert "Иван" in result


class TestBuildCharPrefill:
    def test_empty_returns_empty(self):
        from engine.state_prompts import _build_char_prefill
        result = _build_char_prefill({"characters": {}, "char_names": [], "raw": {}})
        assert result == ""

    def test_structured_chars_formatted(self):
        from engine.state_prompts import _build_char_prefill
        structured = {
            "characters": {"Иван": {"state": "устал", "location": "лес",
                                    "goal": "найти меч", "deep_goal": "", "knows": "", "ignores": ""}},
            "char_names": ["Иван"],
            "raw": {}
        }
        result = _build_char_prefill(structured)
        assert "Иван" in result
        assert "устал" in result

    def test_max_4_chars(self):
        from engine.state_prompts import _build_char_prefill
        chars = {f"Герой{i}": {"state": f"s{i}", "location": "", "goal": "",
                                "deep_goal": "", "knows": "", "ignores": ""}
                 for i in range(6)}
        structured = {"characters": chars, "char_names": list(chars.keys()), "raw": {}}
        result = _build_char_prefill(structured)
        assert sum(1 for n in chars if n in result) <= 4

    def test_freeform_fallback_no_crash(self):
        from engine.state_prompts import _build_char_prefill
        text = "Иван шёл. Иван устал. Мария ждала. Мария волновалась."
        result = _build_char_prefill({"characters": {}, "char_names": [],
                                      "raw": {"global_state": text}})
        assert isinstance(result, str)


class TestPrefillHelpers:
    def test_structured_formats_name(self):
        from engine.state_prompts import _prefill_from_structured
        chars = {"Иван": {"state": "голоден", "location": "таверна",
                          "goal": "поесть", "deep_goal": "", "knows": "", "ignores": ""}}
        result = _prefill_from_structured(chars, ["Иван"])
        assert "Иван" in result and "голоден" in result

    def test_freeform_returns_string(self):
        from engine.state_prompts import _prefill_from_freeform
        result = _prefill_from_freeform("Иван пошёл. Иван устал.")
        assert isinstance(result, str)

    def test_freeform_empty(self):
        from engine.state_prompts import _prefill_from_freeform
        assert _prefill_from_freeform("") == ""


class TestBuildPromptSmoke:
    def _mock_deps(self):
        empty_state = {"global_state": "", "plot_matrix": "", "memory_graph": ""}
        empty_struct = {"characters": {}, "char_names": [], "world": {}, "plot": {}, "raw": {}}
        return empty_state, empty_struct

    def test_quick_returns_string(self, project_id):
        from engine.state_prompts import build_prompt
        state, struct = self._mock_deps()
        with patch("engine.db.get_state", return_value=state), \
             patch("engine.db.get_last_update", return_value=None), \
             patch("engine.db.parse_structured_state", return_value=struct), \
             patch("engine.db.get_director_note", return_value=None):
            result = build_prompt(project_id, 1, "quick", {"name": "T", "genre": "fantasy_epic"})
        assert isinstance(result, str) and len(result) > 0

    def test_quality_returns_string(self, project_id):
        from engine.state_prompts import build_prompt
        state, struct = self._mock_deps()
        with patch("engine.db.get_state", return_value=state), \
             patch("engine.db.get_last_update", return_value=None), \
             patch("engine.db.parse_structured_state", return_value=struct), \
             patch("engine.db.get_director_note", return_value=None):
            result = build_prompt(project_id, 3, "quality", {"name": "T", "genre": "fantasy_epic"})
        assert isinstance(result, str)

    def test_master_returns_string(self, project_id):
        from engine.state_prompts import build_prompt
        state, struct = self._mock_deps()
        with patch("engine.db.get_state", return_value=state), \
             patch("engine.db.get_last_update", return_value=None), \
             patch("engine.db.parse_structured_state", return_value=struct), \
             patch("engine.db.get_director_note", return_value=None):
            result = build_prompt(project_id, 5, "master", {"name": "T", "genre": "fantasy_epic"})
        assert isinstance(result, str)
