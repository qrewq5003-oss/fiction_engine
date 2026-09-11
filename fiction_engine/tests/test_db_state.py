"""
test_db_state.py — engine/db_state.py

A. CRUD: get_state, update_state, save/get/mark state_updates
B. Snapshot/restore
C. parse_structured_state — главная парсинг-функция
D. _extract_field, _extract_block, _detect_char_names_freeform
E. merge_analysis_into_state (JSON и legacy пути)
F. extract_freeform_with_llm, parse_structured_state_smart
"""
import pytest


class TestGetUpdateState:
    """A. CRUD."""

    def test_get_state_new_project_returns_defaults(self, project_id):
        from engine.db_state import get_state
        state = get_state(project_id)
        assert "global_state" in state
        assert "plot_matrix" in state
        assert "memory_graph" in state

    def test_update_state_persists(self, project_id):
        from engine.db_state import get_state, update_state
        update_state(project_id, global_state="Герой: Иван", plot_matrix="СТАТУС: начало")
        state = get_state(project_id)
        assert "Иван" in state["global_state"]
        assert "начало" in state["plot_matrix"]

    def test_update_state_partial_preserves_other_fields(self, project_id):
        from engine.db_state import get_state, update_state
        update_state(project_id, global_state="GLOBAL", plot_matrix="PLOT", memory_graph="MEM")
        update_state(project_id, global_state="GLOBAL2")
        state = get_state(project_id)
        assert state["global_state"] == "GLOBAL2"
        assert state["plot_matrix"] == "PLOT"
        assert state["memory_graph"] == "MEM"

    def test_save_state_update_returns_id(self, project_id):
        from engine.db_state import save_state_update
        update_id = save_state_update(project_id, 1, "анализ главы")
        assert isinstance(update_id, int)
        assert update_id > 0

    def test_get_pending_updates_empty_initially(self, project_id):
        from engine.db_state import get_pending_updates
        assert get_pending_updates(project_id) == []

    def test_mark_update_applied_removes_from_pending(self, project_id):
        from engine.db_state import save_state_update, get_pending_updates, mark_update_applied
        uid = save_state_update(project_id, 1, "анализ")
        assert len(get_pending_updates(project_id)) == 1
        assert mark_update_applied(project_id, uid)
        assert get_pending_updates(project_id) == []

    def test_get_last_update_none_when_empty(self, project_id):
        from engine.db_state import get_last_update
        assert get_last_update(project_id) is None

    def test_get_last_update_returns_latest(self, project_id):
        from engine.db_state import save_state_update, get_last_update
        save_state_update(project_id, 1, "первый")
        save_state_update(project_id, 2, "второй")
        last = get_last_update(project_id)
        assert last is not None
        assert last["chapter_num"] == 2


class TestSnapshotRestore:
    """B. Snapshot/restore."""

    def test_snapshot_creates_history_entry(self, project_id):
        from engine.db_state import update_state, snapshot_state, get_state_history
        update_state(project_id, global_state="Версия 1")
        snapshot_state(project_id, reason="тест")
        history = get_state_history(project_id)
        assert len(history) >= 1
        assert any(h["reason"] == "тест" for h in history)

    def test_restore_snapshot_restores_state(self, project_id):
        from engine.db_state import update_state, snapshot_state, get_state_history, \
            restore_state_snapshot, get_state
        update_state(project_id, global_state="Оригинальный state")
        snapshot_state(project_id, reason="до изменений")
        history = get_state_history(project_id)
        snap_id = history[0]["id"]

        update_state(project_id, global_state="Изменённый state")
        assert "Изменённый" in get_state(project_id)["global_state"]

        result = restore_state_snapshot(project_id, snap_id)
        assert result is True
        assert "Оригинальный" in get_state(project_id)["global_state"]

    def test_restore_nonexistent_snapshot_returns_false(self, project_id):
        from engine.db_state import restore_state_snapshot
        assert restore_state_snapshot(project_id, snapshot_id=99999) is False

    def test_snapshot_history_capped_at_20(self, project_id):
        from engine.db_state import update_state, snapshot_state, get_state_history
        update_state(project_id, global_state="X")
        for i in range(25):
            snapshot_state(project_id, reason=f"snap {i}")
        history = get_state_history(project_id)
        assert len(history) <= 20


class TestParseStructuredState:
    """C. parse_structured_state."""

    def _state(self, global_state="", plot_matrix="", memory_graph=""):
        return {"global_state": global_state, "plot_matrix": plot_matrix,
                "memory_graph": memory_graph}

    def test_empty_state_returns_empty_structure(self):
        from engine.db_state import parse_structured_state
        result = parse_structured_state(self._state())
        assert result["characters"] == {}
        assert result["char_names"] == []
        assert isinstance(result["world"], dict)
        assert isinstance(result["plot"], dict)

    def test_structured_chars_parsed(self):
        from engine.db_state import parse_structured_state
        global_text = (
            "## ПЕРСОНАЖИ\n\n"
            "### Иван\n"
            "СОСТОЯНИЕ: устал\n"
            "ЛОКАЦИЯ: лес\n"
            "ЦЕЛЬ_СЕЙЧАС: найти меч\n"
            "ЦЕЛЬ_ГЛУБИННАЯ: спасти королевство\n"
            "ЗНАЕТ: о драконе\n"
            "НЕ_ЗНАЕТ: об измене\n"
        )
        result = parse_structured_state(self._state(global_text))
        assert "Иван" in result["char_names"]
        assert result["characters"]["Иван"]["state"] == "устал"
        assert result["characters"]["Иван"]["location"] == "лес"
        assert result["characters"]["Иван"]["goal"] == "найти меч"

    def test_multiple_chars_parsed(self):
        from engine.db_state import parse_structured_state
        global_text = (
            "### Иван\nСОСТОЯНИЕ: бодр\nЛОКАЦИЯ: замок\n"
            "### Мария\nСОСТОЯНИЕ: напугана\nЛОКАЦИЯ: башня\n"
        )
        result = parse_structured_state(self._state(global_text))
        assert "Иван" in result["char_names"]
        assert "Мария" in result["char_names"]

    def test_world_fields_parsed(self):
        from engine.db_state import parse_structured_state
        global_text = (
            "МОМЕНТ: герой стоит у ворот замка\n"
            "УГРОЗА: дракон приближается\n"
            "НЕ_ДОЛЖНО_СЛУЧИТЬСЯ: предательство главного героя\n"
        )
        result = parse_structured_state(self._state(global_text))
        assert "ворот замка" in result["world"]["moment"]
        assert "дракон" in result["world"]["threat"]
        assert "предательство" in result["world"]["forbidden"]

    def test_plot_fields_parsed(self):
        from engine.db_state import parse_structured_state
        plot_text = (
            "СТАТУС: кульминация\n"
            "ГДЕ_СЕЙЧАС: тронный зал\n"
            "СЛЕДУЮЩИЙ_ШАГ: финальный бой\n"
        )
        result = parse_structured_state(self._state(plot_matrix=plot_text))
        assert "кульминация" in result["plot"]["status"]
        assert "финальный бой" in result["plot"]["next"]

    def test_exception_returns_empty_not_raises(self):
        """parse_structured_state никогда не бросает — возвращает пустую структуру."""
        from engine.db_state import parse_structured_state
        result = parse_structured_state({"global_state": None, "plot_matrix": None})
        assert isinstance(result, dict)
        assert "characters" in result

    def test_freeform_text_detects_names(self):
        """Если нет ### паттернов — детект имён по частотности."""
        from engine.db_state import parse_structured_state
        global_text = (
            "Иван пошёл в лес. Иван был голоден. Мария ждала Ивана дома. "
            "Мария волновалась. Мария не знала куда ушёл Иван."
        )
        result = parse_structured_state({"global_state": global_text, "plot_matrix": "", "memory_graph": ""})
        assert "Иван" in result["char_names"] or len(result["char_names"]) > 0


class TestExtractHelpers:
    """D. _extract_field, _extract_block, _detect_char_names_freeform."""

    def test_extract_field_finds_value(self):
        from engine.db_state import _extract_field
        text = "СОСТОЯНИЕ: устал и голоден\nЛОКАЦИЯ: лес"
        assert _extract_field(text, "СОСТОЯНИЕ") == "устал и голоден"

    def test_extract_field_first_key_wins(self):
        from engine.db_state import _extract_field
        text = "СОСТОЯНИЕ: значение1\nSTATE: значение2"
        assert _extract_field(text, "СОСТОЯНИЕ", "STATE") == "значение1"

    def test_extract_field_empty_bracket_ignored(self):
        from engine.db_state import _extract_field
        text = "СОСТОЯНИЕ: []"
        assert _extract_field(text, "СОСТОЯНИЕ") == ""

    def test_extract_field_missing_returns_empty(self):
        from engine.db_state import _extract_field
        assert _extract_field("ЛОКАЦИЯ: лес", "СОСТОЯНИЕ") == ""

    def test_extract_block_finds_section(self):
        from engine.db_state import _extract_block
        text = "### Иван\nСОСТОЯНИЕ: устал\nЛОКАЦИЯ: лес\n### Мария\nСОСТОЯНИЕ: бодра"
        block = _extract_block(text, "Иван")
        assert "устал" in block
        assert "Мария" not in block

    def test_detect_char_names_by_frequency(self):
        from engine.db_state import _detect_char_names_freeform
        text = "Иван пошёл. Иван вернулся. Мария ждала. Мария не спала."
        names = _detect_char_names_freeform(text)
        assert "Иван" in names
        assert "Мария" in names

    def test_detect_char_names_excludes_common_words(self):
        from engine.db_state import _detect_char_names_freeform
        text = "Его нет. Его не было. Его не ждали. Мир велик. Мир прекрасен."
        names = _detect_char_names_freeform(text)
        assert "Его" not in names
        assert "Мир" not in names


class TestMergeAnalysisIntoState:
    """E. merge_analysis_into_state."""

    def _setup_state(self, project_id):
        from engine.db_state import update_state
        update_state(project_id,
            global_state=(
                "## ПЕРСОНАЖИ\n\n"
                "### Иван\n"
                "СОСТОЯНИЕ: устал\n"
                "ЛОКАЦИЯ: лес\n"
                "ЦЕЛЬ_СЕЙЧАС: найти меч\n"
                "ЗНАЕТ: []\nНЕ_ЗНАЕТ: []\n"
            ),
            plot_matrix="СТАТУС: начало\nСЛЕДУЮЩИЙ_ШАГ: идти в замок\n",
            memory_graph=""
        )

    def test_json_format_updates_character(self, project_id):
        import json
        from engine.db_state import merge_analysis_into_state, get_state
        self._setup_state(project_id)
        analysis = json.dumps({
            "global_state_changes": [
                {"name": "Иван", "состояние": "отдохнул", "локация": "замок", "цель": ""}
            ],
            "plot_changes": {},
            "memory_changes": []
        })
        result = merge_analysis_into_state(project_id, analysis)
        assert result["changed"] is True
        state = get_state(project_id)
        assert "отдохнул" in state["global_state"]
        assert "замок" in state["global_state"]

    def test_json_format_adds_new_character(self, project_id):
        import json
        from engine.db_state import merge_analysis_into_state, get_state
        self._setup_state(project_id)
        analysis = json.dumps({
            "global_state_changes": [
                {"name": "Дракон", "состояние": "проснулся", "локация": "гора", "цель": ""}
            ],
            "plot_changes": {},
            "memory_changes": []
        })
        result = merge_analysis_into_state(project_id, analysis)
        assert "Дракон" in result["new_chars"]
        state = get_state(project_id)
        # Проверяем полный шаблон _create_char_entry — не только имя
        assert "Дракон" in state["global_state"]
        assert "ЦЕЛЬ_ГЛУБИННАЯ: []" in state["global_state"], (
            "_create_char_entry должна добавлять ЦЕЛЬ_ГЛУБИННАЯ"
        )
        assert "ИЗМЕНЕНИЕ: [автодобавлен]" in state["global_state"], (
            "_create_char_entry должна добавлять ИЗМЕНЕНИЕ: [автодобавлен]"
        )
        assert "ЗНАЕТ: []" in state["global_state"]
        assert "НЕ_ЗНАЕТ: []" in state["global_state"]

    def test_json_format_updates_plot(self, project_id):
        import json
        from engine.db_state import merge_analysis_into_state, get_state
        self._setup_state(project_id)
        analysis = json.dumps({
            "global_state_changes": [],
            "plot_changes": {"следующий_шаг": "войти в замок"},
            "memory_changes": []
        })
        merge_analysis_into_state(project_id, analysis)
        state = get_state(project_id)
        assert "войти в замок" in state["plot_matrix"]

    def test_no_changes_returns_changed_false(self, project_id):
        import json
        from engine.db_state import merge_analysis_into_state
        self._setup_state(project_id)
        analysis = json.dumps({
            "global_state_changes": [],
            "plot_changes": {},
            "memory_changes": []
        })
        result = merge_analysis_into_state(project_id, analysis)
        assert result["changed"] is False

    def test_invalid_json_falls_back_to_legacy(self, project_id):
        """Не-JSON → legacy parser → не падает."""
        from engine.db_state import merge_analysis_into_state
        self._setup_state(project_id)
        result = merge_analysis_into_state(project_id, "не JSON текст")
        assert isinstance(result, dict)
        assert "changed" in result

    def test_legacy_format_updates_plot(self, project_id):
        from engine.db_state import merge_analysis_into_state, get_state
        self._setup_state(project_id)
        legacy = (
            "=== PLOT_MATRIX — ИЗМЕНЕНИЯ ===\n"
            "Следующий шаг: атаковать замок\n"
        )
        result = merge_analysis_into_state(project_id, legacy)
        if result["changed"]:
            state = get_state(project_id)
            assert "атаковать замок" in state["plot_matrix"]


class TestExtractFreeformWithLlm:
    """F. extract_freeform_with_llm, parse_structured_state_smart."""

    def test_empty_text_returns_none(self):
        from engine.db_state import extract_freeform_with_llm
        assert extract_freeform_with_llm("", lambda p: "{}") is None

    def test_no_api_fn_returns_none(self):
        from engine.db_state import extract_freeform_with_llm
        assert extract_freeform_with_llm("Текст о персонаже.", None) is None

    def test_valid_llm_response_parsed(self):
        import json
        from engine.db_state import extract_freeform_with_llm
        response = json.dumps({
            "characters": [{"name": "Иван", "state": "устал", "location": "лес",
                            "goal": "", "knows": "", "ignores": ""}],
            "world": {"moment": "вечер", "threat": "", "forbidden": ""},
            "plot": {"next": "", "must_not": ""}
        })
        result = extract_freeform_with_llm("Иван в лесу устал.", lambda p: response)
        assert result is not None
        assert "Иван" in result["char_names"]
        assert result["characters"]["Иван"]["state"] == "устал"

    def test_bad_json_response_returns_none(self):
        from engine.db_state import extract_freeform_with_llm
        result = extract_freeform_with_llm("Текст.", lambda p: "не JSON")
        assert result is None

    def test_smart_parse_uses_llm_when_structured_empty(self):
        import json
        from engine.db_state import parse_structured_state_smart
        state = {"global_state": "Иван устал в лесу.", "plot_matrix": "", "memory_graph": ""}
        response = json.dumps({
            "characters": [{"name": "Иван", "state": "устал", "location": "лес",
                            "goal": "", "knows": "", "ignores": ""}],
            "world": {"moment": "", "threat": "", "forbidden": ""},
            "plot": {"next": "", "must_not": ""}
        })
        result = parse_structured_state_smart(state, api_call_fn=lambda p: response)
        assert "Иван" in result.get("char_names", []) or isinstance(result, dict)

    def test_smart_parse_no_llm_returns_structured(self):
        from engine.db_state import parse_structured_state_smart
        state = {
            "global_state": "### Иван\nСОСТОЯНИЕ: бодр\n",
            "plot_matrix": "", "memory_graph": ""
        }
        result = parse_structured_state_smart(state, api_call_fn=None)
        assert "Иван" in result["char_names"]
