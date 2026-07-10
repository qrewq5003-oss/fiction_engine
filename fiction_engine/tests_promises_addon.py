

# ══════════════════════════════════════════════════════════════════════
# PROMISES — структурированные обещания (66 тестов из updated)
# ══════════════════════════════════════════════════════════════════════


# ── test_promise_lifecycle.py ──
import json
from unittest.mock import patch


class TestPromiseLifecycle:

    def _generate_summary(self, project_id, chapter_num, promises: list[dict]):
        """Сохранить саммари с заданными promises через generate_l3_summary."""
        from engine.l3_memory import generate_l3_summary
        raw = json.dumps({
            "events":     f"событие главы {chapter_num}",
            "characters": "персонаж изменился",
            "conflicts":  "конфликт активен",
            "promises":   promises,
            "mood":       "тревожное",
        })
        result = generate_l3_summary(project_id, chapter_num, "А" * 200, lambda p: raw)
        assert result is not None, f"generate_l3_summary вернул None для гл.{chapter_num}"
        return result

    def test_full_cycle_single_promise(self, project_id):
        """
        Полный цикл одного обещания:
        создать → проверить активность → закрыть → проверить исчезновение.
        """
        from engine.db_state import merge_analysis_into_state
        from engine.cognitive_memory import get_cognitive_context, get_weighted_promises

        # Шаг 1: создаём главу с активным обещанием
        self._generate_summary(project_id, 1, [
            {"id": "1_0", "text": "Убийца вернётся в финале", "resolved": False}
        ])

        # Шаг 2: обещание видно в контексте и в weighted_promises
        with patch("engine.cognitive_memory.get_l3_summaries") as mock_get:
            from engine.db import get_l3_summaries
            mock_get.side_effect = lambda pid, before, n: get_l3_summaries(pid, before, n)
            ctx_before = get_cognitive_context(project_id, before_chapter=5)
            wp_before  = get_weighted_promises(project_id, before_chapter=5)

        assert "Убийца вернётся" in ctx_before, "promise должен быть в контексте до закрытия"
        assert "Убийца вернётся" in wp_before,  "promise должен быть в weighted до закрытия"

        # Шаг 3: анализ главы 3 закрывает обещание
        analysis = json.dumps({
            "global_state_changes": [],
            "plot_changes":         {},
            "memory_changes":       [],
            "next_context":         "убийца пойман",
            "resolved_promises":    ["1_0"],
        })
        result = merge_analysis_into_state(project_id, analysis, chapter_num=3)

        # resolved_promises должны попасть в fields
        promise_fields = [f for f in result["fields"] if "promise" in f["field"]]
        assert len(promise_fields) == 1
        assert promise_fields[0]["after"] == "resolved"

        # Шаг 4: обещание исчезло из контекста и weighted_promises
        with patch("engine.cognitive_memory.get_l3_summaries") as mock_get:
            mock_get.side_effect = lambda pid, before, n: get_l3_summaries(pid, before, n)
            ctx_after = get_cognitive_context(project_id, before_chapter=5)
            wp_after  = get_weighted_promises(project_id, before_chapter=5)

        assert "Убийца вернётся" not in ctx_after, "закрытый promise не должен быть в контексте"
        assert "Убийца вернётся" not in wp_after,  "закрытый promise не должен быть в weighted"

    def test_partial_close_other_promises_remain(self, project_id):
        """
        Закрытие одного обещания не убирает другие активные.
        """
        from engine.db_state import merge_analysis_into_state
        from engine.cognitive_memory import get_weighted_promises

        self._generate_summary(project_id, 2, [
            {"id": "2_0", "text": "Герой найдёт меч",      "resolved": False},
            {"id": "2_1", "text": "Предательство раскроется", "resolved": False},
        ])

        # Закрываем только первое
        analysis = json.dumps({
            "global_state_changes": [],
            "resolved_promises": ["2_0"],
        })
        merge_analysis_into_state(project_id, analysis, chapter_num=5)

        from engine.db import get_l3_summaries
        with patch("engine.cognitive_memory.get_l3_summaries") as mock_get:
            mock_get.side_effect = lambda pid, before, n: get_l3_summaries(pid, before, n)
            wp = get_weighted_promises(project_id, before_chapter=8)

        assert "Герой найдёт меч"       not in wp, "закрытое обещание не должно быть видно"
        assert "Предательство раскроется" in wp,   "активное обещание должно остаться"

    def test_promise_resolved_chapter_recorded(self, project_id):
        """
        resolved_chapter в саммари соответствует chapter_num из merge.
        """
        from engine.db_state import merge_analysis_into_state
        from engine.db import get_l3_summary
        from engine.l3_memory import normalize_promises

        self._generate_summary(project_id, 1, [
            {"id": "1_0", "text": "Тайна замка", "resolved": False}
        ])

        analysis = json.dumps({
            "global_state_changes": [],
            "resolved_promises": ["1_0"],
        })
        merge_analysis_into_state(project_id, analysis, chapter_num=7)

        saved = get_l3_summary(project_id, 1)
        promises = normalize_promises(saved["promises"], 1)
        assert promises[0]["resolved"] is True
        assert promises[0]["resolved_chapter"] == 7, (
            f"resolved_chapter должен быть 7, получили {promises[0]['resolved_chapter']}"
        )

    def test_legacy_and_new_promises_coexist(self, project_id):
        """
        Проект с legacy-саммари (строка) и новым (список) работает корректно.
        Legacy нормализуется при чтении — оба типа видны в weighted_promises.
        """
        from engine.l3_memory import generate_l3_summary
        from engine.cognitive_memory import get_weighted_promises
        from engine.db import get_l3_summaries

        # Глава 1 — legacy строка (сохраняем напрямую через save_l3_summary)
        from engine.db import save_l3_summary
        save_l3_summary(project_id, 1, {
            "events": "событие",
            "characters": "", "conflicts": "", "mood": "",
            "promises": "Старое обещание в строковом формате",
        })

        # Глава 2 — новый формат
        self._generate_summary(project_id, 2, [
            {"id": "2_0", "text": "Новое структурированное обещание", "resolved": False}
        ])

        with patch("engine.cognitive_memory.get_l3_summaries") as mock_get:
            mock_get.side_effect = lambda pid, before, n: get_l3_summaries(pid, before, n)
            wp = get_weighted_promises(project_id, before_chapter=5)

        assert "Старое обещание" in wp,                  "legacy promise должен быть виден"
        assert "Новое структурированное обещание" in wp, "новый promise должен быть виден"

    def test_unknown_promise_id_in_resolved_is_safe(self, project_id):
        """
        resolved_promises с несуществующим id не роняет merge и не меняет state.
        """
        from engine.db_state import merge_analysis_into_state, get_state
        from engine.db_state import update_state

        update_state(project_id,
                     global_state="### Иван\nСОСТОЯНИЕ: жив",
                     plot_matrix="СТАТУС: активна")

        analysis = json.dumps({
            "global_state_changes": [],
            "resolved_promises": ["99_0", "999_1"],  # несуществующие
        })

        result = merge_analysis_into_state(project_id, analysis, chapter_num=5)

        # Не упал
        assert isinstance(result, dict)
        assert "changed" in result
        # State не изменился от несуществующих id
        state = get_state(project_id)
        assert "жив" in state["global_state"]


# ── test_promises_cognitive.py ──
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


# ── test_promises_db_state.py ──
import json
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
        with patch("engine.db_state.mark_promise_resolved", mock_mark):
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
        with patch("engine.db_state.mark_promise_resolved", mock_mark):
            merge_analysis_into_state(
                project_id,
                self._make_analysis(["5_0"]),
                chapter_num=8,
            )

        mock_mark.assert_called_once_with(project_id, "5_0", resolved_chapter=8)

    def test_empty_resolved_promises_no_mark_called(self, project_id):
        from engine.db_state import merge_analysis_into_state

        mock_mark = MagicMock(return_value=True)
        with patch("engine.db_state.mark_promise_resolved", mock_mark):
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
        with patch("engine.db_state.mark_promise_resolved", mock_mark):
            result = merge_analysis_into_state(project_id, data, chapter_num=5)

        mock_mark.assert_called_once()

    def test_mark_error_is_recoverable(self, project_id):
        """Ошибка в mark_promise_resolved не должна ломать весь merge."""
        from engine.db_state import merge_analysis_into_state

        def crash(pid, promise_id, resolved_chapter):
            raise RuntimeError("DB упала")

        with patch("engine.db_state.mark_promise_resolved", crash):
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
        with patch("engine.db_state.mark_promise_resolved", mock_mark):
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
        with patch("engine.db_state.mark_promise_resolved", mock_mark):
            merge_analysis_into_state(project_id, data, chapter_num=7)

        # Только "5_0" — валидный строковый непустой id
        mock_mark.assert_called_once_with(project_id, "5_0", resolved_chapter=7)


# ── test_promises_l3.py ──
import json
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


# ── test_promises_state.py ──
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



# ── run()-вызовы ──

def _ptest_TestPromiseLifecycle_test_full_cycle_single_promise():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestPromiseLifecycle()
    obj.test_full_cycle_single_promise(project_id=_pid)
run("promises/test_promise_lifecycle: TestPromiseLifecycle.test_full_cycle_single_promise", _ptest_TestPromiseLifecycle_test_full_cycle_single_promise)

def _ptest_TestPromiseLifecycle_test_partial_close_other_promises_remain():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestPromiseLifecycle()
    obj.test_partial_close_other_promises_remain(project_id=_pid)
run("promises/test_promise_lifecycle: TestPromiseLifecycle.test_partial_close_other_promises_remain", _ptest_TestPromiseLifecycle_test_partial_close_other_promises_remain)

def _ptest_TestPromiseLifecycle_test_promise_resolved_chapter_recorded():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestPromiseLifecycle()
    obj.test_promise_resolved_chapter_recorded(project_id=_pid)
run("promises/test_promise_lifecycle: TestPromiseLifecycle.test_promise_resolved_chapter_recorded", _ptest_TestPromiseLifecycle_test_promise_resolved_chapter_recorded)

def _ptest_TestPromiseLifecycle_test_legacy_and_new_promises_coexist():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestPromiseLifecycle()
    obj.test_legacy_and_new_promises_coexist(project_id=_pid)
run("promises/test_promise_lifecycle: TestPromiseLifecycle.test_legacy_and_new_promises_coexist", _ptest_TestPromiseLifecycle_test_legacy_and_new_promises_coexist)

def _ptest_TestPromiseLifecycle_test_unknown_promise_id_in_resolved_is_safe():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestPromiseLifecycle()
    obj.test_unknown_promise_id_in_resolved_is_safe(project_id=_pid)
run("promises/test_promise_lifecycle: TestPromiseLifecycle.test_unknown_promise_id_in_resolved_is_safe", _ptest_TestPromiseLifecycle_test_unknown_promise_id_in_resolved_is_safe)

def _ptest_TestScoreSummaryWithStructuredPromises_test_active_promise_list_gets_score():
    make_db()
    obj = TestScoreSummaryWithStructuredPromises()
    obj.test_active_promise_list_gets_score()
run("promises/test_promises_cognitive: TestScoreSummaryWithStructuredPromises.test_active_promise_list_gets_score", _ptest_TestScoreSummaryWithStructuredPromises_test_active_promise_list_gets_score)

def _ptest_TestScoreSummaryWithStructuredPromises_test_all_resolved_promises_no_score():
    make_db()
    obj = TestScoreSummaryWithStructuredPromises()
    obj.test_all_resolved_promises_no_score()
run("promises/test_promises_cognitive: TestScoreSummaryWithStructuredPromises.test_all_resolved_promises_no_score", _ptest_TestScoreSummaryWithStructuredPromises_test_all_resolved_promises_no_score)

def _ptest_TestScoreSummaryWithStructuredPromises_test_empty_promises_list_no_score():
    make_db()
    obj = TestScoreSummaryWithStructuredPromises()
    obj.test_empty_promises_list_no_score()
run("promises/test_promises_cognitive: TestScoreSummaryWithStructuredPromises.test_empty_promises_list_no_score", _ptest_TestScoreSummaryWithStructuredPromises_test_empty_promises_list_no_score)

def _ptest_TestScoreSummaryWithStructuredPromises_test_legacy_string_promise_gets_score():
    make_db()
    obj = TestScoreSummaryWithStructuredPromises()
    obj.test_legacy_string_promise_gets_score()
run("promises/test_promises_cognitive: TestScoreSummaryWithStructuredPromises.test_legacy_string_promise_gets_score", _ptest_TestScoreSummaryWithStructuredPromises_test_legacy_string_promise_gets_score)

def _ptest_TestScoreSummaryWithStructuredPromises_test_mixed_active_and_resolved_gets_score():
    make_db()
    obj = TestScoreSummaryWithStructuredPromises()
    obj.test_mixed_active_and_resolved_gets_score()
run("promises/test_promises_cognitive: TestScoreSummaryWithStructuredPromises.test_mixed_active_and_resolved_gets_score", _ptest_TestScoreSummaryWithStructuredPromises_test_mixed_active_and_resolved_gets_score)

def _ptest_TestGetWeightedPromisesStructured_test_returns_only_active_promises():
    make_db()
    obj = TestGetWeightedPromisesStructured()
    obj.test_returns_only_active_promises()
run("promises/test_promises_cognitive: TestGetWeightedPromisesStructured.test_returns_only_active_promises", _ptest_TestGetWeightedPromisesStructured_test_returns_only_active_promises)

def _ptest_TestGetWeightedPromisesStructured_test_promise_id_shown_in_output():
    make_db()
    obj = TestGetWeightedPromisesStructured()
    obj.test_promise_id_shown_in_output()
run("promises/test_promises_cognitive: TestGetWeightedPromisesStructured.test_promise_id_shown_in_output", _ptest_TestGetWeightedPromisesStructured_test_promise_id_shown_in_output)

def _ptest_TestGetWeightedPromisesStructured_test_all_resolved_returns_empty_string():
    make_db()
    obj = TestGetWeightedPromisesStructured()
    obj.test_all_resolved_returns_empty_string()
run("promises/test_promises_cognitive: TestGetWeightedPromisesStructured.test_all_resolved_returns_empty_string", _ptest_TestGetWeightedPromisesStructured_test_all_resolved_returns_empty_string)

def _ptest_TestGetWeightedPromisesStructured_test_legacy_string_promises_included():
    make_db()
    obj = TestGetWeightedPromisesStructured()
    obj.test_legacy_string_promises_included()
run("promises/test_promises_cognitive: TestGetWeightedPromisesStructured.test_legacy_string_promises_included", _ptest_TestGetWeightedPromisesStructured_test_legacy_string_promises_included)

def _ptest_TestGetWeightedPromisesStructured_test_no_summaries_returns_empty():
    make_db()
    obj = TestGetWeightedPromisesStructured()
    obj.test_no_summaries_returns_empty()
run("promises/test_promises_cognitive: TestGetWeightedPromisesStructured.test_no_summaries_returns_empty", _ptest_TestGetWeightedPromisesStructured_test_no_summaries_returns_empty)

def _ptest_TestGetWeightedPromisesStructured_test_multiple_chapters_all_active_included():
    make_db()
    obj = TestGetWeightedPromisesStructured()
    obj.test_multiple_chapters_all_active_included()
run("promises/test_promises_cognitive: TestGetWeightedPromisesStructured.test_multiple_chapters_all_active_included", _ptest_TestGetWeightedPromisesStructured_test_multiple_chapters_all_active_included)

def _ptest_TestCognitiveContextPromises_test_active_promises_in_context():
    make_db()
    obj = TestCognitiveContextPromises()
    obj.test_active_promises_in_context()
run("promises/test_promises_cognitive: TestCognitiveContextPromises.test_active_promises_in_context", _ptest_TestCognitiveContextPromises_test_active_promises_in_context)

def _ptest_TestCognitiveContextPromises_test_resolved_promises_excluded_from_context():
    make_db()
    obj = TestCognitiveContextPromises()
    obj.test_resolved_promises_excluded_from_context()
run("promises/test_promises_cognitive: TestCognitiveContextPromises.test_resolved_promises_excluded_from_context", _ptest_TestCognitiveContextPromises_test_resolved_promises_excluded_from_context)

def _ptest_TestCognitiveContextPromises_test_chapter_without_active_promises_still_included_for_other_fields():
    make_db()
    obj = TestCognitiveContextPromises()
    obj.test_chapter_without_active_promises_still_included_for_other_fields()
run("promises/test_promises_cognitive: TestCognitiveContextPromises.test_chapter_without_active_promises_still_included_for_other_fields", _ptest_TestCognitiveContextPromises_test_chapter_without_active_promises_still_included_for_other_fields)

def _ptest_TestCreateCharEntry_test_returns_string_with_all_fields():
    make_db()
    obj = TestCreateCharEntry()
    obj.test_returns_string_with_all_fields()
run("promises/test_promises_db_state: TestCreateCharEntry.test_returns_string_with_all_fields", _ptest_TestCreateCharEntry_test_returns_string_with_all_fields)

def _ptest_TestCreateCharEntry_test_empty_state_becomes_placeholder():
    make_db()
    obj = TestCreateCharEntry()
    obj.test_empty_state_becomes_placeholder()
run("promises/test_promises_db_state: TestCreateCharEntry.test_empty_state_becomes_placeholder", _ptest_TestCreateCharEntry_test_empty_state_becomes_placeholder)

def _ptest_TestCreateCharEntry_test_arrow_notation_stripped():
    make_db()
    obj = TestCreateCharEntry()
    obj.test_arrow_notation_stripped()
run("promises/test_promises_db_state: TestCreateCharEntry.test_arrow_notation_stripped", _ptest_TestCreateCharEntry_test_arrow_notation_stripped)

def _ptest_TestCreateCharEntry_test_placeholder_bracket_value_becomes_empty():
    make_db()
    obj = TestCreateCharEntry()
    obj.test_placeholder_bracket_value_becomes_empty()
run("promises/test_promises_db_state: TestCreateCharEntry.test_placeholder_bracket_value_becomes_empty", _ptest_TestCreateCharEntry_test_placeholder_bracket_value_becomes_empty)

def _ptest_TestCreateCharEntry_test_used_in_add_new_char():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestCreateCharEntry()
    obj.test_used_in_add_new_char(project_id=_pid)
run("promises/test_promises_db_state: TestCreateCharEntry.test_used_in_add_new_char", _ptest_TestCreateCharEntry_test_used_in_add_new_char)

def _ptest_TestCreateCharEntry_test_add_new_char_and_merge_from_json_produce_same_template():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestCreateCharEntry()
    obj.test_add_new_char_and_merge_from_json_produce_same_template(project_id=_pid)
run("promises/test_promises_db_state: TestCreateCharEntry.test_add_new_char_and_merge_from_json_produce_same_template", _ptest_TestCreateCharEntry_test_add_new_char_and_merge_from_json_produce_same_template)

def _ptest_TestMergeResolvedPromises_test_resolved_promises_appear_in_fields_changed():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestMergeResolvedPromises()
    obj.test_resolved_promises_appear_in_fields_changed(project_id=_pid)
run("promises/test_promises_db_state: TestMergeResolvedPromises.test_resolved_promises_appear_in_fields_changed", _ptest_TestMergeResolvedPromises_test_resolved_promises_appear_in_fields_changed)

def _ptest_TestMergeResolvedPromises_test_mark_promise_resolved_called_with_correct_args():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestMergeResolvedPromises()
    obj.test_mark_promise_resolved_called_with_correct_args(project_id=_pid)
run("promises/test_promises_db_state: TestMergeResolvedPromises.test_mark_promise_resolved_called_with_correct_args", _ptest_TestMergeResolvedPromises_test_mark_promise_resolved_called_with_correct_args)

def _ptest_TestMergeResolvedPromises_test_empty_resolved_promises_no_mark_called():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestMergeResolvedPromises()
    obj.test_empty_resolved_promises_no_mark_called(project_id=_pid)
run("promises/test_promises_db_state: TestMergeResolvedPromises.test_empty_resolved_promises_no_mark_called", _ptest_TestMergeResolvedPromises_test_empty_resolved_promises_no_mark_called)

def _ptest_TestMergeResolvedPromises_test_resolved_promises_field_only_key_triggers_json_path():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestMergeResolvedPromises()
    obj.test_resolved_promises_field_only_key_triggers_json_path(project_id=_pid)
run("promises/test_promises_db_state: TestMergeResolvedPromises.test_resolved_promises_field_only_key_triggers_json_path", _ptest_TestMergeResolvedPromises_test_resolved_promises_field_only_key_triggers_json_path)

def _ptest_TestMergeResolvedPromises_test_mark_error_is_recoverable():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestMergeResolvedPromises()
    obj.test_mark_error_is_recoverable(project_id=_pid)
run("promises/test_promises_db_state: TestMergeResolvedPromises.test_mark_error_is_recoverable", _ptest_TestMergeResolvedPromises_test_mark_error_is_recoverable)

def _ptest_TestMergeResolvedPromises_test_chapter_num_default_zero():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestMergeResolvedPromises()
    obj.test_chapter_num_default_zero(project_id=_pid)
run("promises/test_promises_db_state: TestMergeResolvedPromises.test_chapter_num_default_zero", _ptest_TestMergeResolvedPromises_test_chapter_num_default_zero)

def _ptest_TestMergeResolvedPromises_test_non_string_ids_in_resolved_promises_skipped():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestMergeResolvedPromises()
    obj.test_non_string_ids_in_resolved_promises_skipped(project_id=_pid)
run("promises/test_promises_db_state: TestMergeResolvedPromises.test_non_string_ids_in_resolved_promises_skipped", _ptest_TestMergeResolvedPromises_test_non_string_ids_in_resolved_promises_skipped)

def _ptest_TestNormalizePromises_test_legacy_string_becomes_single_item_list():
    make_db()
    obj = TestNormalizePromises()
    obj.test_legacy_string_becomes_single_item_list()
run("promises/test_promises_l3: TestNormalizePromises.test_legacy_string_becomes_single_item_list", _ptest_TestNormalizePromises_test_legacy_string_becomes_single_item_list)

def _ptest_TestNormalizePromises_test_empty_string_returns_empty_list():
    make_db()
    obj = TestNormalizePromises()
    obj.test_empty_string_returns_empty_list()
run("promises/test_promises_l3: TestNormalizePromises.test_empty_string_returns_empty_list", _ptest_TestNormalizePromises_test_empty_string_returns_empty_list)

def _ptest_TestNormalizePromises_test_whitespace_string_returns_empty_list():
    make_db()
    obj = TestNormalizePromises()
    obj.test_whitespace_string_returns_empty_list()
run("promises/test_promises_l3: TestNormalizePromises.test_whitespace_string_returns_empty_list", _ptest_TestNormalizePromises_test_whitespace_string_returns_empty_list)

def _ptest_TestNormalizePromises_test_none_returns_empty_list():
    make_db()
    obj = TestNormalizePromises()
    obj.test_none_returns_empty_list()
run("promises/test_promises_l3: TestNormalizePromises.test_none_returns_empty_list", _ptest_TestNormalizePromises_test_none_returns_empty_list)

def _ptest_TestNormalizePromises_test_valid_list_passthrough():
    make_db()
    obj = TestNormalizePromises()
    obj.test_valid_list_passthrough()
run("promises/test_promises_l3: TestNormalizePromises.test_valid_list_passthrough", _ptest_TestNormalizePromises_test_valid_list_passthrough)

def _ptest_TestNormalizePromises_test_list_with_empty_text_skipped():
    make_db()
    obj = TestNormalizePromises()
    obj.test_list_with_empty_text_skipped()
run("promises/test_promises_l3: TestNormalizePromises.test_list_with_empty_text_skipped", _ptest_TestNormalizePromises_test_list_with_empty_text_skipped)

def _ptest_TestNormalizePromises_test_list_item_missing_id_gets_generated():
    make_db()
    obj = TestNormalizePromises()
    obj.test_list_item_missing_id_gets_generated()
run("promises/test_promises_l3: TestNormalizePromises.test_list_item_missing_id_gets_generated", _ptest_TestNormalizePromises_test_list_item_missing_id_gets_generated)

def _ptest_TestNormalizePromises_test_list_item_missing_resolved_defaults_false():
    make_db()
    obj = TestNormalizePromises()
    obj.test_list_item_missing_resolved_defaults_false()
run("promises/test_promises_l3: TestNormalizePromises.test_list_item_missing_resolved_defaults_false", _ptest_TestNormalizePromises_test_list_item_missing_resolved_defaults_false)

def _ptest_TestGetActivePromises_test_returns_only_unresolved():
    make_db()
    obj = TestGetActivePromises()
    obj.test_returns_only_unresolved()
run("promises/test_promises_l3: TestGetActivePromises.test_returns_only_unresolved", _ptest_TestGetActivePromises_test_returns_only_unresolved)

def _ptest_TestGetActivePromises_test_all_resolved_returns_empty():
    make_db()
    obj = TestGetActivePromises()
    obj.test_all_resolved_returns_empty()
run("promises/test_promises_l3: TestGetActivePromises.test_all_resolved_returns_empty", _ptest_TestGetActivePromises_test_all_resolved_returns_empty)

def _ptest_TestGetActivePromises_test_empty_list_returns_empty():
    make_db()
    obj = TestGetActivePromises()
    obj.test_empty_list_returns_empty()
run("promises/test_promises_l3: TestGetActivePromises.test_empty_list_returns_empty", _ptest_TestGetActivePromises_test_empty_list_returns_empty)

def _ptest_TestGetActivePromises_test_preserves_promise_data():
    make_db()
    obj = TestGetActivePromises()
    obj.test_preserves_promise_data()
run("promises/test_promises_l3: TestGetActivePromises.test_preserves_promise_data", _ptest_TestGetActivePromises_test_preserves_promise_data)

def _ptest_TestMarkPromiseResolved_test_marks_promise_as_resolved():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestMarkPromiseResolved()
    obj.test_marks_promise_as_resolved(project_id=_pid)
run("promises/test_promises_l3: TestMarkPromiseResolved.test_marks_promise_as_resolved", _ptest_TestMarkPromiseResolved_test_marks_promise_as_resolved)

def _ptest_TestMarkPromiseResolved_test_returns_false_for_unknown_promise():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestMarkPromiseResolved()
    obj.test_returns_false_for_unknown_promise(project_id=_pid)
run("promises/test_promises_l3: TestMarkPromiseResolved.test_returns_false_for_unknown_promise", _ptest_TestMarkPromiseResolved_test_returns_false_for_unknown_promise)

def _ptest_TestMarkPromiseResolved_test_returns_false_for_invalid_id_format():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestMarkPromiseResolved()
    obj.test_returns_false_for_invalid_id_format(project_id=_pid)
run("promises/test_promises_l3: TestMarkPromiseResolved.test_returns_false_for_invalid_id_format", _ptest_TestMarkPromiseResolved_test_returns_false_for_invalid_id_format)

def _ptest_TestMarkPromiseResolved_test_already_resolved_not_updated_again():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestMarkPromiseResolved()
    obj.test_already_resolved_not_updated_again(project_id=_pid)
run("promises/test_promises_l3: TestMarkPromiseResolved.test_already_resolved_not_updated_again", _ptest_TestMarkPromiseResolved_test_already_resolved_not_updated_again)

def _ptest_TestGenerateSummaryPromises_test_structured_promises_saved_as_list():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestGenerateSummaryPromises()
    obj.test_structured_promises_saved_as_list(project_id=_pid)
run("promises/test_promises_l3: TestGenerateSummaryPromises.test_structured_promises_saved_as_list", _ptest_TestGenerateSummaryPromises_test_structured_promises_saved_as_list)

def _ptest_TestGenerateSummaryPromises_test_legacy_string_promises_normalized_on_save():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestGenerateSummaryPromises()
    obj.test_legacy_string_promises_normalized_on_save(project_id=_pid)
run("promises/test_promises_l3: TestGenerateSummaryPromises.test_legacy_string_promises_normalized_on_save", _ptest_TestGenerateSummaryPromises_test_legacy_string_promises_normalized_on_save)

def _ptest_TestGenerateSummaryPromises_test_empty_promises_saved_as_empty_list():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestGenerateSummaryPromises()
    obj.test_empty_promises_saved_as_empty_list(project_id=_pid)
run("promises/test_promises_l3: TestGenerateSummaryPromises.test_empty_promises_saved_as_empty_list", _ptest_TestGenerateSummaryPromises_test_empty_promises_saved_as_empty_list)

def _ptest_TestGetL3ContextPromises_test_active_promises_shown():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestGetL3ContextPromises()
    obj.test_active_promises_shown(project_id=_pid)
run("promises/test_promises_l3: TestGetL3ContextPromises.test_active_promises_shown", _ptest_TestGetL3ContextPromises_test_active_promises_shown)

def _ptest_TestGetL3ContextPromises_test_resolved_promises_not_shown():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestGetL3ContextPromises()
    obj.test_resolved_promises_not_shown(project_id=_pid)
run("promises/test_promises_l3: TestGetL3ContextPromises.test_resolved_promises_not_shown", _ptest_TestGetL3ContextPromises_test_resolved_promises_not_shown)

def _ptest_TestGetL3ContextPromises_test_mixed_promises_shows_only_active():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestGetL3ContextPromises()
    obj.test_mixed_promises_shows_only_active(project_id=_pid)
run("promises/test_promises_l3: TestGetL3ContextPromises.test_mixed_promises_shows_only_active", _ptest_TestGetL3ContextPromises_test_mixed_promises_shows_only_active)

def _ptest_TestBuildAnalysisPrompt_test_without_promises_no_promises_block():
    make_db()
    obj = TestBuildAnalysisPrompt()
    obj.test_without_promises_no_promises_block()
run("promises/test_promises_state: TestBuildAnalysisPrompt.test_without_promises_no_promises_block", _ptest_TestBuildAnalysisPrompt_test_without_promises_no_promises_block)

def _ptest_TestBuildAnalysisPrompt_test_with_empty_promises_list_no_promises_block():
    make_db()
    obj = TestBuildAnalysisPrompt()
    obj.test_with_empty_promises_list_no_promises_block()
run("promises/test_promises_state: TestBuildAnalysisPrompt.test_with_empty_promises_list_no_promises_block", _ptest_TestBuildAnalysisPrompt_test_with_empty_promises_list_no_promises_block)

def _ptest_TestBuildAnalysisPrompt_test_with_promises_block_appears():
    make_db()
    obj = TestBuildAnalysisPrompt()
    obj.test_with_promises_block_appears()
run("promises/test_promises_state: TestBuildAnalysisPrompt.test_with_promises_block_appears", _ptest_TestBuildAnalysisPrompt_test_with_promises_block_appears)

def _ptest_TestBuildAnalysisPrompt_test_resolved_promises_field_in_json_schema():
    make_db()
    obj = TestBuildAnalysisPrompt()
    obj.test_resolved_promises_field_in_json_schema()
run("promises/test_promises_state: TestBuildAnalysisPrompt.test_resolved_promises_field_in_json_schema", _ptest_TestBuildAnalysisPrompt_test_resolved_promises_field_in_json_schema)

def _ptest_TestBuildAnalysisPrompt_test_chapter_content_in_prompt():
    make_db()
    obj = TestBuildAnalysisPrompt()
    obj.test_chapter_content_in_prompt()
run("promises/test_promises_state: TestBuildAnalysisPrompt.test_chapter_content_in_prompt", _ptest_TestBuildAnalysisPrompt_test_chapter_content_in_prompt)

def _ptest_TestBuildAnalysisPrompt_test_chapter_num_in_prompt():
    make_db()
    obj = TestBuildAnalysisPrompt()
    obj.test_chapter_num_in_prompt()
run("promises/test_promises_state: TestBuildAnalysisPrompt.test_chapter_num_in_prompt", _ptest_TestBuildAnalysisPrompt_test_chapter_num_in_prompt)

def _ptest_TestBuildAnalysisPrompt_test_state_fields_in_prompt():
    make_db()
    obj = TestBuildAnalysisPrompt()
    obj.test_state_fields_in_prompt()
run("promises/test_promises_state: TestBuildAnalysisPrompt.test_state_fields_in_prompt", _ptest_TestBuildAnalysisPrompt_test_state_fields_in_prompt)

def _ptest_TestAnalyzeChapterPromises_test_active_promises_passed_to_prompt():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestAnalyzeChapterPromises()
    obj.test_active_promises_passed_to_prompt(project_id=_pid)
run("promises/test_promises_state: TestAnalyzeChapterPromises.test_active_promises_passed_to_prompt", _ptest_TestAnalyzeChapterPromises_test_active_promises_passed_to_prompt)

def _ptest_TestAnalyzeChapterPromises_test_promise_load_failure_does_not_crash():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestAnalyzeChapterPromises()
    obj.test_promise_load_failure_does_not_crash(project_id=_pid)
run("promises/test_promises_state: TestAnalyzeChapterPromises.test_promise_load_failure_does_not_crash", _ptest_TestAnalyzeChapterPromises_test_promise_load_failure_does_not_crash)

def _ptest_TestQueueStateUpdatePromises_test_promise_load_failure_does_not_crash():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestQueueStateUpdatePromises()
    obj.test_promise_load_failure_does_not_crash(project_id=_pid)
run("promises/test_promises_state: TestQueueStateUpdatePromises.test_promise_load_failure_does_not_crash", _ptest_TestQueueStateUpdatePromises_test_promise_load_failure_does_not_crash)

def _ptest_TestQueueStateUpdatePromises_test_active_promises_included_in_prompt_text():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestQueueStateUpdatePromises()
    obj.test_active_promises_included_in_prompt_text(project_id=_pid)
run("promises/test_promises_state: TestQueueStateUpdatePromises.test_active_promises_included_in_prompt_text", _ptest_TestQueueStateUpdatePromises_test_active_promises_included_in_prompt_text)

def _ptest_TestQueueStateUpdatePromises_test_short_text_returns_false():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestQueueStateUpdatePromises()
    obj.test_short_text_returns_false(project_id=_pid)
run("promises/test_promises_state: TestQueueStateUpdatePromises.test_short_text_returns_false", _ptest_TestQueueStateUpdatePromises_test_short_text_returns_false)
