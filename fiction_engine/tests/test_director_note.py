"""
test_director_note.py — engine/director_note.py

generate_director_note:
1. Возвращает строку при успешном LLM-вызове
2. Сохраняет заметку в БД
3. Возвращает None при коротком ответе LLM
4. Возвращает None при исключении LLM (не бросает)
5. Хвост главы попадает в промпт
6. global_state попадает в промпт
"""
import pytest
from unittest.mock import patch


class TestGenerateDirectorNote:
    def test_returns_string_on_success(self, project_id):
        from engine.director_note import generate_director_note
        state = {"global_state": "Иван устал", "plot_matrix": ""}
        with patch("engine.db.save_director_note"):
            result = generate_director_note(
                project_id, 1, "А" * 200, state,
                api_call_fn=lambda p: "Не торопить реакцию. Тишина важнее."
            )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_saves_to_db(self, project_id):
        from engine.director_note import generate_director_note
        state = {"global_state": "", "plot_matrix": ""}
        with patch("engine.db.save_director_note") as mock_save:
            generate_director_note(
                project_id, 1, "А" * 200, state,
                api_call_fn=lambda p: "Заметка для следующей главы."
            )
        mock_save.assert_called_once()

    def test_returns_none_when_short_response(self, project_id):
        from engine.director_note import generate_director_note
        state = {"global_state": "", "plot_matrix": ""}
        result = generate_director_note(
            project_id, 1, "А" * 200, state,
            api_call_fn=lambda p: "кор"  # < 10 символов
        )
        assert result is None

    def test_returns_none_on_exception(self, project_id):
        from engine.director_note import generate_director_note
        state = {"global_state": "", "plot_matrix": ""}
        result = generate_director_note(
            project_id, 1, "А" * 200, state,
            api_call_fn=lambda p: (_ for _ in ()).throw(RuntimeError("LLM упал"))
        )
        assert result is None

    def test_chapter_tail_in_prompt(self, project_id):
        from engine.director_note import generate_director_note
        captured = {}
        state = {"global_state": "", "plot_matrix": ""}
        UNIQUE = "УНИКАЛЬНЫЙ_ХВОСТ_ГЛАВЫ_XYZ"

        def api_fn(prompt):
            captured["prompt"] = prompt
            return "Заметка на следующую главу."

        with patch("engine.db.save_director_note"):
            generate_director_note(project_id, 1, "Текст " * 50 + UNIQUE, state, api_fn)

        assert UNIQUE in captured.get("prompt", "")

    def test_global_state_in_prompt(self, project_id):
        from engine.director_note import generate_director_note
        captured = {}
        UNIQUE = "УНИКАЛЬНЫЙ_СТЕЙТ_ИВАНА_XYZ"
        state = {"global_state": UNIQUE, "plot_matrix": ""}

        def api_fn(prompt):
            captured["prompt"] = prompt
            return "Заметка."

        with patch("engine.db.save_director_note"):
            generate_director_note(project_id, 1, "А" * 200, state, api_fn)

        assert UNIQUE in captured.get("prompt", "")
