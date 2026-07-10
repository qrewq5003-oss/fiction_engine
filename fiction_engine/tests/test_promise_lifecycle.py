"""
test_promise_lifecycle.py — интеграционный тест сквозного цикла promises.

Проверяет весь путь:
  1. generate_l3_summary сохраняет promises как структурированный список
  2. merge_analysis_into_state с resolved_promises вызывает mark_promise_resolved
  3. После закрытия promise не появляется в get_cognitive_context
  4. После закрытия promise не появляется в get_weighted_promises
  5. Другие активные promises остаются видимы

Это единственное место где тестируется сквозная цепочка без моков на БД.
"""
import json
import pytest
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
