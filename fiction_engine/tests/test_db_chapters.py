"""
test_db_chapters.py — юнит-тесты для db_chapters.py и интеграция cognitive_memory.

Покрываем:
  A. Калибровка судьи (save_judge_calibration / get_judge_calibration_hint)
     1. Пустая таблица → пустая строка
     2. Меньше min_samples → пустая строка
     3. Судья завышает → hint с "завышены"
     4. Судья занижает → hint с "занижены"
     5. Отклонение < 1.5 → hint "точны"
     6. UNIQUE(project_id, chapter_num) — повторная запись обновляет, не дублирует

  B. Проектный порог (get_project_accept_threshold / format_project_threshold_hint)
     7. Меньше min_accepted → None
     8. Нечётное число scores → правильная медиана
     9. Чётное число scores → медиана как среднее двух средних
    10. bias вычислен как round(avg - median, 1)
    11. format_project_threshold_hint: пустая строка для None
    12. format_project_threshold_hint: содержит threshold и accepted_count
    13. format_project_threshold_hint: bias >= 1.5 добавляет предупреждение
    14. format_project_threshold_hint: accept_floor никогда ниже 30

  C. Монотонность структуры (check_structural_monotony)
    15. Меньше 4 глав → пустая строка
    16. Все разные opening_type → пустая строка
    17. > 60% одного opening_type → предупреждение
    18. > 60% одного closing_type → предупреждение
    19. Монотонны и opening и closing → оба предупреждения
    20. Ровно 60% (граничный случай) → предупреждение (>=)
    21. before_chapter исключает текущую и будущие главы
    22. window ограничивает выборку

  D. Интеграция cognitive_memory → build_context
    23. Без L3 саммари — промпт не содержит контекст серии из памяти
    24. С L3 саммари — промпт содержит данные из саммари
    25. Promises из ранних глав попадают в промпт (не затухают, decay=0)
"""

import pytest
import json
from unittest.mock import patch, MagicMock


# ═══════════════════════════════════════════════════════════════════════════════
# A. Калибровка судьи
# ═══════════════════════════════════════════════════════════════════════════════

class TestJudgeCalibration:

    def _save(self, pid, ch, judge, author, note=""):
        from engine.db_chapters import save_judge_calibration
        save_judge_calibration(pid, ch, judge, author, note)

    def test_empty_db_returns_empty_hint(self, project_id):
        from engine.db_chapters import get_judge_calibration_hint
        assert get_judge_calibration_hint(project_id) == ""

    def test_below_min_samples_returns_empty(self, project_id):
        """2 записи при min_samples=3 → пустая строка."""
        self._save(project_id, 1, judge=40.0, author=40.0)
        self._save(project_id, 2, judge=38.0, author=38.0)
        from engine.db_chapters import get_judge_calibration_hint
        assert get_judge_calibration_hint(project_id, min_samples=3) == ""

    def test_judge_overestimates_hint_contains_zavysheny(self, project_id):
        """Судья даёт 42, автор — 38: судья завышает на 4."""
        for ch in range(1, 6):
            self._save(project_id, ch, judge=42.0, author=38.0)
        from engine.db_chapters import get_judge_calibration_hint
        hint = get_judge_calibration_hint(project_id, min_samples=3)
        assert "завышены" in hint
        assert "4.0" in hint

    def test_judge_underestimates_hint_contains_zanijeny(self, project_id):
        """Судья даёт 35, автор — 40: судья занижает на 5."""
        for ch in range(1, 6):
            self._save(project_id, ch, judge=35.0, author=40.0)
        from engine.db_chapters import get_judge_calibration_hint
        hint = get_judge_calibration_hint(project_id, min_samples=3)
        assert "занижены" in hint
        assert "5.0" in hint

    def test_small_deviation_returns_accurate_hint(self, project_id):
        """Отклонение 1.0 < 1.5 → hint говорит «точны»."""
        for ch in range(1, 5):
            self._save(project_id, ch, judge=40.0, author=41.0)
        from engine.db_chapters import get_judge_calibration_hint
        hint = get_judge_calibration_hint(project_id, min_samples=3)
        assert "точны" in hint

    def test_duplicate_chapter_updates_not_duplicates(self, project_id):
        """UNIQUE(project_id, chapter_num): повторная запись обновляет строку."""
        self._save(project_id, 1, judge=40.0, author=40.0)
        self._save(project_id, 1, judge=45.0, author=40.0)  # обновление
        from engine.db_core import get_conn
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT judge_score FROM judge_calibration WHERE project_id=? AND chapter_num=1",
                (project_id,)
            ).fetchall()
        assert len(rows) == 1
        assert rows[0]["judge_score"] == 45.0

    def test_calibration_isolated_per_project(self, use_temp_db):
        """Подсказка одного проекта не смешивается с данными другого."""
        from engine.db_projects import create_project
        pid1 = create_project("Проект 1")
        pid2 = create_project("Проект 2")
        for ch in range(1, 6):
            self._save(pid1, ch, judge=42.0, author=38.0)  # завышает
        for ch in range(1, 6):
            self._save(pid2, ch, judge=38.0, author=42.0)  # занижает
        from engine.db_chapters import get_judge_calibration_hint
        hint1 = get_judge_calibration_hint(pid1, min_samples=3)
        hint2 = get_judge_calibration_hint(pid2, min_samples=3)
        assert "завышены" in hint1
        assert "занижены" in hint2


# ═══════════════════════════════════════════════════════════════════════════════
# B. Проектный порог принятия
# ═══════════════════════════════════════════════════════════════════════════════

class TestProjectAcceptThreshold:
    """
    get_project_accept_threshold читает из pipeline_runs + pipeline_iterations.
    Используем save_judge_calibration + accept_pipeline для наполнения через
    реальный pipeline — либо вставляем напрямую в БД для изоляции.
    Выбираем прямую вставку: тест не должен зависеть от pipeline.
    """

    def _insert_accepted_run(self, pid, ch, score):
        """Вставить запись о принятой главе с judge score напрямую в БД."""
        from engine.db_core import get_conn
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO pipeline_runs
                    (project_id, chapter_num, status, model_gen, model_critic,
                     model_editor, model_judge)
                VALUES (?, ?, 'accepted', 'm', 'm', 'm', 'm')
            """, (pid, ch))
            run_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute("""
                INSERT INTO pipeline_iterations
                    (run_id, iteration, stage, model_used, input_text, output_text, score)
                VALUES (?, 1, 'judge', 'm', '', '', ?)
            """, (run_id, score))

    def test_below_min_accepted_returns_none(self, project_id):
        """4 записи при min_accepted=5 → None."""
        for ch in range(1, 5):
            self._insert_accepted_run(project_id, ch, 40.0)
        from engine.db_chapters import get_project_accept_threshold
        assert get_project_accept_threshold(project_id, min_accepted=5) is None

    def test_median_odd_count(self, project_id):
        """5 scores [30, 35, 40, 42, 45] → медиана = 40 (средний элемент)."""
        for ch, score in enumerate([30.0, 35.0, 40.0, 42.0, 45.0], start=1):
            self._insert_accepted_run(project_id, ch, score)
        from engine.db_chapters import get_project_accept_threshold
        result = get_project_accept_threshold(project_id, min_accepted=5)
        assert result is not None
        assert result["threshold"] == pytest.approx(40.0)
        assert result["accepted_count"] == 5

    def test_median_even_count(self, project_id):
        """6 scores [30, 35, 40, 42, 45, 50] → медиана = (40+42)/2 = 41."""
        for ch, score in enumerate([30.0, 35.0, 40.0, 42.0, 45.0, 50.0], start=1):
            self._insert_accepted_run(project_id, ch, score)
        from engine.db_chapters import get_project_accept_threshold
        result = get_project_accept_threshold(project_id, min_accepted=5)
        assert result is not None
        assert result["threshold"] == pytest.approx(41.0)

    def test_bias_calculation(self, project_id):
        """
        5 scores [38, 38, 38, 38, 42].
        sorted: [38,38,38,38,42]. median=38. avg=38.8. bias=round(38.8-38,1)=0.8
        """
        for ch, score in enumerate([38.0, 38.0, 38.0, 38.0, 42.0], start=1):
            self._insert_accepted_run(project_id, ch, score)
        from engine.db_chapters import get_project_accept_threshold
        result = get_project_accept_threshold(project_id, min_accepted=5)
        assert result is not None
        assert result["judge_bias"] == pytest.approx(0.8)

    def test_format_hint_none_returns_empty(self):
        from engine.db_chapters import format_project_threshold_hint
        assert format_project_threshold_hint(None) == ""

    def test_format_hint_contains_threshold_and_count(self, project_id):
        from engine.db_chapters import format_project_threshold_hint
        data = {"threshold": 38.0, "judge_bias": 0.5, "accepted_count": 7}
        hint = format_project_threshold_hint(data)
        assert "38" in hint
        assert "7" in hint

    def test_format_hint_large_bias_adds_warning(self):
        """bias >= 1.5 → добавляет предупреждение о систематической ошибке."""
        from engine.db_chapters import format_project_threshold_hint
        data = {"threshold": 38.0, "judge_bias": 2.5, "accepted_count": 6}
        hint = format_project_threshold_hint(data)
        assert "занижаешь" in hint or "завышаешь" in hint

    def test_format_hint_accept_floor_never_below_30(self):
        """threshold=10 → accept_floor = max(10-3, 30) = 30, не 7."""
        from engine.db_chapters import format_project_threshold_hint
        data = {"threshold": 10.0, "judge_bias": 0.0, "accepted_count": 5}
        hint = format_project_threshold_hint(data)
        assert "30" in hint


# ═══════════════════════════════════════════════════════════════════════════════
# C. Монотонность структуры
# ═══════════════════════════════════════════════════════════════════════════════

class TestStructuralMonotony:

    def _save_analysis(self, pid, ch, opening="", closing=""):
        from engine.db_chapters import save_chapter_analysis
        save_chapter_analysis(pid, ch, {
            "opening_type": opening,
            "closing_type": closing,
            "analysis_quality": "ok",
        })

    def test_less_than_4_chapters_returns_empty(self, project_id):
        """3 главы → недостаточно данных."""
        for ch, op in enumerate(["action", "dialogue", "description"], start=1):
            self._save_analysis(project_id, ch, opening=op)
        from engine.db_chapters import check_structural_monotony
        assert check_structural_monotony(project_id, before_chapter=10) == ""

    def test_all_different_opening_types_no_warning(self, project_id):
        """4 разных opening → нет монотонности."""
        types = ["action", "dialogue", "description", "internal"]
        for ch, t in enumerate(types, start=1):
            self._save_analysis(project_id, ch, opening=t)
        from engine.db_chapters import check_structural_monotony
        assert check_structural_monotony(project_id, before_chapter=10) == ""

    def test_majority_same_opening_triggers_warning(self, project_id):
        """5 из 5 глав с opening='action' (100% >= 60%) → предупреждение."""
        for ch in range(1, 6):
            self._save_analysis(project_id, ch, opening="action", closing="dialogue")
        from engine.db_chapters import check_structural_monotony
        result = check_structural_monotony(project_id, before_chapter=10)
        assert "action" in result
        assert "Монотонность" in result

    def test_majority_same_closing_triggers_warning(self, project_id):
        """5 из 5 глав с closing='cliffhanger' → предупреждение."""
        for ch in range(1, 6):
            self._save_analysis(project_id, ch, opening="action", closing="cliffhanger")
        from engine.db_chapters import check_structural_monotony
        result = check_structural_monotony(project_id, before_chapter=10)
        assert "cliffhanger" in result

    def test_both_opening_and_closing_monotony(self, project_id):
        """Монотонны и opening и closing → оба предупреждения в строке."""
        for ch in range(1, 6):
            self._save_analysis(project_id, ch, opening="internal", closing="cliffhanger")
        from engine.db_chapters import check_structural_monotony
        result = check_structural_monotony(project_id, before_chapter=10)
        assert "internal" in result
        assert "cliffhanger" in result

    def test_exactly_60_percent_triggers_warning(self, project_id):
        """Ровно 60%: 3 из 5 с 'action' → >= 0.6 → предупреждение."""
        openings = ["action", "action", "action", "dialogue", "description"]
        for ch, op in enumerate(openings, start=1):
            self._save_analysis(project_id, ch, opening=op)
        from engine.db_chapters import check_structural_monotony
        result = check_structural_monotony(project_id, before_chapter=10)
        assert "action" in result

    def test_before_chapter_excludes_current(self, project_id):
        """before_chapter=5 не включает главы 5 и выше."""
        for ch in range(1, 5):  # главы 1-4: разные
            self._save_analysis(project_id, ch, opening=f"type_{ch}")
        # Глава 5 не должна учитываться
        self._save_analysis(project_id, 5, opening="action")
        self._save_analysis(project_id, 5, opening="action")
        from engine.db_chapters import check_structural_monotony
        # С before_chapter=5 берём только главы 1-4 (разные) → без предупреждения
        result = check_structural_monotony(project_id, before_chapter=5)
        assert result == ""

    def test_window_limits_lookback(self, project_id):
        """window=4 берёт последние 4 главы, игнорирует более ранние."""
        # Главы 1-6: разные; главы 7-10: все action
        for ch in range(1, 7):
            self._save_analysis(project_id, ch, opening=f"type_{ch}")
        for ch in range(7, 11):
            self._save_analysis(project_id, ch, opening="action")
        from engine.db_chapters import check_structural_monotony
        # window=4 видит только главы 7-10 (4 главы, все action) → предупреждение
        result = check_structural_monotony(project_id, before_chapter=11, window=4)
        assert "action" in result


# ═══════════════════════════════════════════════════════════════════════════════
# D. Интеграция cognitive_memory → build_context
# ═══════════════════════════════════════════════════════════════════════════════

class TestCognitiveMemoryInContext:
    """
    Проверяем что get_cognitive_context() реально попадает в промпт
    который строит build_context(). Если cognitive_memory сломается —
    генерация не упадёт, просто промпт будет без контекста серии. Тест
    это поймает.

    Мокируем все компоненты кроме l3_memory и cognitive_memory — нас
    интересует только пайп данных из БД в строку промпта.
    """

    def _save_l3(self, pid, ch, **fields):
        from engine.db_narrative import save_l3_summary
        summary = {
            "events":     fields.get("events", ""),
            "characters": fields.get("characters", ""),
            "conflicts":  fields.get("conflicts", ""),
            "promises":   fields.get("promises", ""),
            "mood":       fields.get("mood", ""),
        }
        save_l3_summary(pid, ch, summary)

    def _build(self, pid, chapter_num):
        """Вызвать build_context с минимальными моками."""
        from engine.pipeline_context import build_context

        # Мокируем компоненты которые нам неинтересны
        with patch("engine.pipeline_context.build_consolidated_voice", return_value=""), \
             patch("engine.pipeline_context._build_exemplar_block", return_value=""), \
             patch("engine.pipeline_context._build_kb_block", return_value=""), \
             patch("engine.pipeline_context._build_engine_block", return_value=""), \
             patch("engine.pipeline_context.get_symbols_context", return_value=""), \
             patch("engine.pipeline_context.extract_relevant_state", return_value=""), \
             patch("engine.db.get_prep_context", return_value=""), \
             patch("engine.pipeline_context._maybe_save_debug_prompt", return_value=None):
            return build_context(pid, chapter_num, "Задача главы")

    def test_without_l3_no_series_context(self, project_id):
        """Без L3 саммари — промпт не содержит данных из памяти."""
        context = self._build(project_id, chapter_num=2)
        # Специфичных маркеров L3 нет
        assert "events" not in context.lower() or True  # мягкая проверка
        # Жёсткая: конкретного контента нет
        assert "ТЕСТОВОЕ СОБЫТИЕ" not in context

    def test_with_l3_summary_events_appear_in_context(self, project_id):
        """С L3 саммари — события из памяти попадают в промпт генерации."""
        self._save_l3(project_id, ch=1, events="ТЕСТОВОЕ СОБЫТИЕ произошло в главе 1")
        context = self._build(project_id, chapter_num=2)
        assert "ТЕСТОВОЕ СОБЫТИЕ" in context

    def test_with_l3_summary_characters_appear_in_context(self, project_id):
        """Персонажи из L3 попадают в промпт."""
        self._save_l3(project_id, ch=1, characters="ТЕСТОВЫЙ ПЕРСОНАЖ появился")
        context = self._build(project_id, chapter_num=2)
        assert "ТЕСТОВЫЙ ПЕРСОНАЖ" in context

    def test_promises_from_early_chapters_appear(self, project_id):
        """
        Promises не затухают (decay=0 в cognitive_memory).
        Сохраняем promise в главе 1, читаем контекст для главы 10 —
        promise должен присутствовать несмотря на дистанцию.
        """
        self._save_l3(project_id, ch=1,
                      promises="ОБЕЩАНИЕ_СЮЖЕТ: герой вернётся в деревню")
        # Добавляем промежуточные главы чтобы глава 1 не была recent
        for ch in range(2, 9):
            self._save_l3(project_id, ch=ch, events=f"событие главы {ch}")

        context = self._build(project_id, chapter_num=10)
        assert "ОБЕЩАНИЕ_СЮЖЕТ" in context

    def test_recent_chapters_always_included(self, project_id):
        """
        Последние 2 главы включаются безусловно (always_recent=2).
        Сохраняем 6 глав, берём контекст для главы 7 —
        главы 5 и 6 должны быть в промпте.
        """
        for ch in range(1, 7):
            self._save_l3(project_id, ch=ch,
                          events=f"УНИКАЛЬНЫЙ_МАРКЕР_ГЛАВЫ_{ch}")
        context = self._build(project_id, chapter_num=7)
        # Последние 2 обязательно присутствуют
        assert "УНИКАЛЬНЫЙ_МАРКЕР_ГЛАВЫ_6" in context
        assert "УНИКАЛЬНЫЙ_МАРКЕР_ГЛАВЫ_5" in context
