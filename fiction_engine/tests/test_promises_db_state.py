"""
test_promises_db_state.py — тесты изменений в db_state.py.

Покрывает:
  A. _create_char_entry — единственный шаблон нового персонажа
  B. merge_analysis_into_state — поле resolved_promises
  C. chapter_num передаётся в mark_promise_resolved
"""
import json
import pytest
from unittest.mock import patch, MagicMock


# ─── A. _create_char_entry ────────────────────────────────────────────────────

class TestCreateCharEntry:

    def test_returns_string_with_all_fields(self):
        from engine.db_state import _create_char_entry
        entry = _create_char_entry("Иван", "испуган", "лес", "спастись")
        assert "### Иван" in entry
        assert "СОСТОЯНИЕ: испуган" in entry
        assert "ЛОКАЦИЯ: лес" in entry
        assert "ЦЕЛЬ_СЕЙЧАС: спастись" in entry
        assert "ЦЕЛЬ_ГЛУБИННАЯ: []" in entry
        assert "ЗНАЕТ: []" in entry
        assert "НЕ_ЗНАЕТ: []" in entry
        assert "ИЗМЕНЕНИЕ: [автодобавлен]" in entry

    def test_empty_state_becomes_placeholder(self):
        from engine.db_state import _create_char_entry
        entry = _create_char_entry("Мария", "", "", "")
        assert "СОСТОЯНИЕ: []" in entry
        assert "ЛОКАЦИЯ: []" in entry
        assert "ЦЕЛЬ_СЕЙЧАС: []" in entry

    def test_arrow_notation_stripped(self):
        """Значения вида 'старое → новое' должны сохранять только правую часть."""
        from engine.db_state import _create_char_entry
        entry = _create_char_entry("Иван", "живой → мёртвый", "дом → лес", "")
        assert "мёртвый" in entry
        assert "лес" in entry
        assert "→" not in entry

    def test_placeholder_bracket_value_becomes_empty(self):
        """Значения вида '[что-то]' считаются плейсхолдерами."""
        from engine.db_state import _create_char_entry
        entry = _create_char_entry("Иван", "[неизвестно]", "дом", "")
        assert "СОСТОЯНИЕ: []" in entry

    def test_used_in_add_new_char(self, project_id):
        """_add_new_char должна использовать _create_char_entry — содержит все поля."""
        from engine.db_state import _add_new_char
        global_text = "## ПЕРСОНАЖИ\n"
        new_chars = []
        result = _add_new_char("Новый", "Section:\nсостояние: радостный\nлокация: замок\nцель: найти клад",
                               global_text, lambda *a: None, new_chars)
        assert "ЦЕЛЬ_ГЛУБИННАЯ: []" in result
        assert "ИЗМЕНЕНИЕ: [автодобавлен]" in result
        assert "Новый" in new_chars

    def test_add_new_char_and_merge_from_json_produce_same_template(self, project_id):
        """
        Ключевой инвариант: оба пути создания персонажа дают одинаковый шаблон.
        Проверяем что оба содержат ЦЕЛЬ_ГЛУБИННАЯ и ИЗМЕНЕНИЕ.
        """
        from engine.db_state import _add_new_char, _create_char_entry

        new_chars_1 = []
        global_text = "## ПЕРСОНАЖИ\n"
        result_add = _add_new_char(
            "Персонаж",
            "Section:\nсостояние: грустный\nлокация: лес\nцель: выжить",
            global_text, lambda *a: None, new_chars_1
        )

        result_entry = _create_char_entry("Персонаж", "грустный", "лес", "выжить")

        # Оба должны иметь одинаковый набор обязательных полей
        for field in ("ЦЕЛЬ_ГЛУБИННАЯ: []", "ЗНАЕТ: []", "НЕ_ЗНАЕТ: []", "ИЗМЕНЕНИЕ: [автодобавлен]"):
            assert field in result_add, f"_add_new_char: отсутствует поле {field}"
            assert field in result_entry, f"_create_char_entry: отсутствует поле {field}"


# ─── B. merge_analysis_into_state — resolved_promises ────────────────────────

class TestMergeResolvedPromises:

    def _make_analysis(self, resolved_ids: list[str], extra: dict | None = None) -> str:
        data = {
            "global_state_changes": [],
            "plot_changes": {},
            "memory_changes": [],
            "next_context": "контекст",
            "resolved_promises": resolved_ids,
        }
        if extra:
            data.update(extra)
        return json.dumps(data)

    def test_resolved_promises_appear_in_fields_changed(self, project_id):
        from engine.db_state import merge_analysis_into_state

        mock_mark = MagicMock(return_value=True)
        with patch("engine.l3_memory.mark_promise_resolved", mock_mark):
            result = merge_analysis_into_state(
                project_id,
                self._make_analysis(["5_0", "3_1"]),
                chapter_num=7,
            )

        # Закрытые обещания должны быть в fields
        promise_fields = [f for f in result["fields"] if "promise" in f["field"]]
        assert len(promise_fields) == 2
        ids_in_fields = {f["field"].split(".")[-1] for f in promise_fields}
        assert "5_0" in ids_in_fields
        assert "3_1" in ids_in_fields

    def test_mark_promise_resolved_called_with_correct_args(self, project_id):
        from engine.db_state import merge_analysis_into_state

        mock_mark = MagicMock(return_value=True)
        with patch("engine.l3_memory.mark_promise_resolved", mock_mark):
            merge_analysis_into_state(
                project_id,
                self._make_analysis(["5_0"]),
                chapter_num=8,
            )

        mock_mark.assert_called_once_with(project_id, "5_0", resolved_chapter=8)

    def test_empty_resolved_promises_no_mark_called(self, project_id):
        from engine.db_state import merge_analysis_into_state

        mock_mark = MagicMock(return_value=True)
        with patch("engine.l3_memory.mark_promise_resolved", mock_mark):
            merge_analysis_into_state(
                project_id,
                self._make_analysis([]),
                chapter_num=5,
            )

        mock_mark.assert_not_called()

    def test_resolved_promises_field_only_key_triggers_json_path(self, project_id):
        """JSON с только resolved_promises (без других ключей) должен идти по JSON-пути."""
        from engine.db_state import merge_analysis_into_state

        data = json.dumps({"resolved_promises": ["2_0"]})
        mock_mark = MagicMock(return_value=True)
        with patch("engine.l3_memory.mark_promise_resolved", mock_mark):
            result = merge_analysis_into_state(project_id, data, chapter_num=5)

        mock_mark.assert_called_once()

    def test_mark_error_is_recoverable(self, project_id):
        """Ошибка в mark_promise_resolved не должна ломать весь merge."""
        from engine.db_state import merge_analysis_into_state

        def crash(pid, promise_id, resolved_chapter):
            raise RuntimeError("DB упала")

        with patch("engine.l3_memory.mark_promise_resolved", crash):
            result = merge_analysis_into_state(
                project_id,
                self._make_analysis(["5_0"]),
                chapter_num=6,
            )
        # Merge должен вернуть результат, не упасть
        assert isinstance(result, dict)
        assert "changed" in result

    def test_chapter_num_default_zero(self, project_id):
        """Обратная совместимость: chapter_num=0 по умолчанию, старые вызовы не ломаются."""
        from engine.db_state import merge_analysis_into_state

        mock_mark = MagicMock(return_value=True)
        with patch("engine.l3_memory.mark_promise_resolved", mock_mark):
            # Вызов без chapter_num — как было раньше
            merge_analysis_into_state(
                project_id,
                self._make_analysis(["1_0"]),
            )

        mock_mark.assert_called_once_with(project_id, "1_0", resolved_chapter=0)

    def test_non_string_ids_in_resolved_promises_skipped(self, project_id):
        """Некорректные id (числа, None) должны фильтроваться без ошибок."""
        from engine.db_state import merge_analysis_into_state

        data = json.dumps({
            "global_state_changes": [],
            "resolved_promises": [None, 123, "5_0", ""],
        })
        mock_mark = MagicMock(return_value=True)
        with patch("engine.l3_memory.mark_promise_resolved", mock_mark):
            merge_analysis_into_state(project_id, data, chapter_num=7)

        # Только "5_0" — валидный строковый непустой id
        mock_mark.assert_called_once_with(project_id, "5_0", resolved_chapter=7)
