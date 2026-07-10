"""
test_property_based.py — property-based тесты с hypothesis.

Запуск:
    pytest tests/test_property_based.py -v
    pytest tests/test_property_based.py -v --hypothesis-seed=0

КЛЮЧЕВОЕ АРХИТЕКТУРНОЕ РЕШЕНИЕ: project_id создаётся ВНУТРИ тела @given-теста,
не через pytest fixture. Иначе hypothesis вызывает тело 300 раз в рамках одного
fixture-вызова → данные из примера N накапливаются в БД → пример N+1 видит
чужие данные → FlakyFailure.

НАЙДЕННЫЕ БАГИ (подтверждены прогоном):
  1. check_structural_monotony: 1/1 opening = 100% >= 60% → ложное срабатывание.
     Патч: if openings: → if len(openings) >= 3:
     Аналогично для closings.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.modules.setdefault("openai", MagicMock())
sys.modules.setdefault("anthropic", MagicMock())
if not hasattr(sys.modules["openai"], "OpenAI"):
    sys.modules["openai"].OpenAI = MagicMock()

from hypothesis import given, assume, settings, HealthCheck
from hypothesis import strategies as st


# ---- Стратегии ---------------------------------------------------------------

judge_score = st.floats(min_value=0.0, max_value=100.0,
                        allow_nan=False, allow_infinity=False)

scores_list = st.lists(judge_score, min_size=5, max_size=20)

opening_types = st.sampled_from(
    ["action", "dialogue", "description", "internal", ""]
)
closing_types = st.sampled_from(
    ["action", "dialogue", "description", "internal", "cliffhanger", ""]
)


# ---- Fixtures ----------------------------------------------------------------

@pytest.fixture(autouse=True)
def use_temp_db(tmp_path):
    db_file = tmp_path / "test.db"
    with patch("engine.db_core.DB_PATH", db_file):
        from engine.db_core import init_db
        init_db()
        yield db_file


def make_project():
    """Создать новый проект для каждого hypothesis-примера."""
    from engine.db_projects import create_project
    return create_project("test", "фэнтези")


# ---- Helpers -----------------------------------------------------------------

def insert_accepted_runs(pid, scores):
    from engine.db_core import get_conn
    with get_conn() as conn:
        for ch, score in enumerate(scores, start=1):
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


def save_analysis(pid, ch, opening, closing):
    from engine.db_chapters import save_chapter_analysis
    save_chapter_analysis(pid, ch, {
        "opening_type": opening,
        "closing_type": closing,
        "analysis_quality": "ok",
    })


def python_median(scores):
    s = sorted(scores)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


# ==============================================================================
# 1. get_project_accept_threshold
# ==============================================================================

class TestThresholdProperties:

    @given(scores=scores_list)
    @settings(max_examples=200)
    def test_threshold_equals_median(self, scores):
        """threshold == медиана последних 20 scores (SQL LIMIT 20)."""
        pid = make_project()
        insert_accepted_runs(pid, scores)
        from engine.db_chapters import get_project_accept_threshold
        result = get_project_accept_threshold(pid, min_accepted=5)
        assert result is not None
        effective = scores[-20:]
        expected = round(python_median(effective), 1)
        assert result["threshold"] == pytest.approx(expected, abs=0.05)

    @given(scores=scores_list)
    @settings(max_examples=200)
    def test_threshold_within_min_max_range(self, scores):
        """
        Медиана всегда в [min, max].
        Проверяет: один outlier 100.0 из 19 нулей, все одинаковые.
        """
        pid = make_project()
        insert_accepted_runs(pid, scores)
        from engine.db_chapters import get_project_accept_threshold
        result = get_project_accept_threshold(pid, min_accepted=5)
        assert result is not None
        effective = scores[-20:]
        # round(median, 1) может незначительно выйти за float-границы
        assert round(min(effective), 1) - 0.1 <= result["threshold"] <= round(max(effective), 1) + 0.1

    @given(scores=scores_list)
    @settings(max_examples=200)
    def test_accepted_count_capped_at_sql_limit(self, scores):
        """accepted_count == min(len(scores), 20). SQL LIMIT 20."""
        pid = make_project()
        insert_accepted_runs(pid, scores)
        from engine.db_chapters import get_project_accept_threshold
        result = get_project_accept_threshold(pid, min_accepted=5)
        assert result is not None
        assert result["accepted_count"] == min(len(scores), 20)

    @given(scores=scores_list)
    @settings(max_examples=150)
    def test_bias_is_round_avg_minus_median(self, scores):
        """
        judge_bias == round(avg - median, 1).
        Hypothesis найдёт: все одинаковые → bias=0.0, один outlier → bias≠0.
        """
        pid = make_project()
        insert_accepted_runs(pid, scores)
        from engine.db_chapters import get_project_accept_threshold
        result = get_project_accept_threshold(pid, min_accepted=5)
        assert result is not None
        effective = scores[-20:]
        expected_bias = round(sum(effective) / len(effective) - python_median(effective), 1)
        assert result["judge_bias"] == pytest.approx(expected_bias, abs=0.15)

    @given(n=st.integers(min_value=1, max_value=4))
    @settings(max_examples=50)
    def test_below_min_accepted_always_none(self, n):
        """n < 5 → всегда None. Hypothesis проверит 1, 2, 3, 4."""
        pid = make_project()
        insert_accepted_runs(pid, [42.0] * n)
        from engine.db_chapters import get_project_accept_threshold
        assert get_project_accept_threshold(pid, min_accepted=5) is None

    @given(v=st.floats(min_value=0.0, max_value=100.0,
                       allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_identical_scores_zero_bias(self, v):
        """
        Все scores одинаковые → avg == median → bias == 0.0.
        Проверяет: v=0.0, v=100.0, v=0.1+0.2 (float precision).
        """
        pid = make_project()
        insert_accepted_runs(pid, [v] * 7)
        from engine.db_chapters import get_project_accept_threshold
        result = get_project_accept_threshold(pid, min_accepted=5)
        assert result is not None
        assert abs(result["judge_bias"]) <= 0.1


# ==============================================================================
# 2. format_project_threshold_hint
# ==============================================================================

class TestFormatHintProperties:

    @given(
        threshold=st.floats(min_value=0.0, max_value=100.0,
                            allow_nan=False, allow_infinity=False),
        bias=st.floats(min_value=-20.0, max_value=20.0,
                       allow_nan=False, allow_infinity=False),
        count=st.integers(min_value=5, max_value=20),
    )
    @settings(max_examples=500)
    def test_accept_floor_never_below_30(self, threshold, bias, count):
        """
        accept_floor = max(threshold - 3, 30) → в hint всегда >= 30.
        Используем f"{floor:.0f}" для сравнения — это то что делает функция.
        """
        from engine.db_chapters import format_project_threshold_hint
        t = round(threshold, 1)
        data = {"threshold": t, "judge_bias": round(bias, 1), "accepted_count": count}
        hint = format_project_threshold_hint(data)
        floor = max(t - 3.0, 30.0)
        # Функция использует :.0f (математическое округление), не int()
        floor_str = f"{floor:.0f}"
        assert floor_str in hint, f"floor={floor} → '{floor_str}' not in: {hint}"

    @given(
        threshold=st.floats(min_value=0.0, max_value=100.0,
                            allow_nan=False, allow_infinity=False),
        bias=st.floats(min_value=-20.0, max_value=20.0,
                       allow_nan=False, allow_infinity=False),
        count=st.integers(min_value=5, max_value=20),
    )
    @settings(max_examples=500)
    def test_always_nonempty_string(self, threshold, bias, count):
        """Для любых валидных данных — непустая строка, никогда None или crash."""
        from engine.db_chapters import format_project_threshold_hint
        data = {"threshold": round(threshold, 1),
                "judge_bias": round(bias, 1),
                "accepted_count": count}
        result = format_project_threshold_hint(data)
        assert isinstance(result, str) and len(result) > 0

    @given(
        threshold=st.floats(min_value=0.0, max_value=100.0,
                            allow_nan=False, allow_infinity=False),
        bias=st.floats(min_value=1.5, max_value=20.0,
                       allow_nan=False, allow_infinity=False),
        count=st.integers(min_value=5, max_value=20),
    )
    @settings(max_examples=200)
    def test_positive_bias_gte_1_5_says_zanizhaesh(self, threshold, bias, count):
        """bias >= 1.5 → 'занижаешь'."""
        from engine.db_chapters import format_project_threshold_hint
        data = {"threshold": round(threshold, 1),
                "judge_bias": round(bias, 1),
                "accepted_count": count}
        assert "занижаешь" in format_project_threshold_hint(data)

    @given(
        threshold=st.floats(min_value=0.0, max_value=100.0,
                            allow_nan=False, allow_infinity=False),
        bias=st.floats(min_value=-20.0, max_value=-1.5,
                       allow_nan=False, allow_infinity=False),
        count=st.integers(min_value=5, max_value=20),
    )
    @settings(max_examples=200)
    def test_negative_bias_lte_minus_1_5_says_zavyshaesh(self, threshold, bias, count):
        """bias <= -1.5 → 'завышаешь'."""
        from engine.db_chapters import format_project_threshold_hint
        data = {"threshold": round(threshold, 1),
                "judge_bias": round(bias, 1),
                "accepted_count": count}
        assert "завышаешь" in format_project_threshold_hint(data)

    @given(
        threshold=st.floats(min_value=0.0, max_value=100.0,
                            allow_nan=False, allow_infinity=False),
        bias=st.floats(min_value=-20.0, max_value=20.0,
                       allow_nan=False, allow_infinity=False),
        count=st.integers(min_value=5, max_value=20),
    )
    @settings(max_examples=200)
    def test_small_bias_no_direction_warning(self, threshold, bias, count):
        """
        |round(bias, 1)| < 1.5 → ни 'занижаешь', ни 'завышаешь'.
        assume применяется ПОСЛЕ round — иначе -1.46875 → -1.5 проскакивает.
        """
        from engine.db_chapters import format_project_threshold_hint
        b = round(bias, 1)
        assume(abs(b) < 1.5)  # проверяем ПОСЛЕ round, как делает функция
        data = {"threshold": round(threshold, 1),
                "judge_bias": b,
                "accepted_count": count}
        hint = format_project_threshold_hint(data)
        assert "занижаешь" not in hint
        assert "завышаешь" not in hint


# ==============================================================================
# 3. check_structural_monotony
# ==============================================================================

class TestMonotonyProperties:
    """
    Баг исправлен в db_chapters.py: if openings: → if len(openings) >= 3:
    test_sparse_opening_no_false_positive теперь должен проходить.
    """

    @given(
        opening=opening_types,
        closing=closing_types,
        n=st.integers(min_value=4, max_value=20),
    )
    @settings(max_examples=200)
    def test_always_returns_string(self, opening, closing, n):
        """Никогда не падает, всегда возвращает str."""
        from engine.db_chapters import check_structural_monotony
        pid = make_project()
        for ch in range(1, n + 1):
            save_analysis(pid, ch, opening, closing)
        result = check_structural_monotony(pid, before_chapter=n + 1)
        assert isinstance(result, str)

    @given(n=st.integers(min_value=4, max_value=15))
    @settings(max_examples=100)
    def test_sparse_opening_no_false_positive(self, n):
        """
        БАГ-ТЕСТ (был баг, сейчас исправлен):
        n-1 глав с пустым opening + 1 глава с 'action'.
        openings = ["action"] (1 элемент).
        ДО патча: 1/1 = 100% >= 60% → ложное срабатывание.
        ПОСЛЕ патча (len >= 3): нет предупреждения.
        """
        from engine.db_chapters import check_structural_monotony
        pid = make_project()
        for ch in range(1, n):
            save_analysis(pid, ch, opening="", closing="cliffhanger")
        save_analysis(pid, n, opening="action", closing="cliffhanger")
        result = check_structural_monotony(pid, before_chapter=n + 1)
        assert "открываются через «action»" not in result, (
            f"False positive: 1/1 opening triggered monotony with {n} total chapters"
        )

    @given(n_chapters=st.integers(min_value=1, max_value=3))
    @settings(max_examples=50)
    def test_fewer_than_4_qualifying_rows_returns_empty(self, n_chapters):
        """< 4 строк с непустым opening/closing → пустая строка."""
        from engine.db_chapters import check_structural_monotony
        pid = make_project()
        for ch in range(1, n_chapters + 1):
            save_analysis(pid, ch, opening="action", closing="cliffhanger")
        result = check_structural_monotony(pid, before_chapter=n_chapters + 1)
        assert result == ""

    @given(
        dominant=st.sampled_from(["action", "dialogue", "description", "internal"]),
        n_dominant=st.integers(min_value=3, max_value=6),
        n_other=st.integers(min_value=0, max_value=2),
    )
    @settings(max_examples=200)
    def test_dominant_above_60pct_triggers_warning(self, dominant, n_dominant, n_other):
        """
        dominant / total >= 60% → предупреждение.
        assume(total <= 8): все главы в window=8.
        assume(n_dominant >= 3): минимум для нового условия len >= 3.
        """
        from engine.db_chapters import check_structural_monotony
        assume(n_dominant + n_other >= 4)
        assume(n_dominant + n_other <= 8)
        pct = n_dominant / (n_dominant + n_other)
        assume(pct >= 0.6)

        pid = make_project()
        ch = 1
        for _ in range(n_dominant):
            save_analysis(pid, ch, opening=dominant, closing="")
            ch += 1
        others = [t for t in ["action", "dialogue", "description", "internal"]
                  if t != dominant]
        for i in range(n_other):
            save_analysis(pid, ch, opening=others[i % len(others)], closing="")
            ch += 1

        result = check_structural_monotony(pid, before_chapter=ch)
        assert dominant in result, (
            f"{n_dominant}/{n_dominant + n_other} = {pct:.0%} of '{dominant}'"
        )

    @given(
        dominant=st.sampled_from(["action", "dialogue", "description", "internal"]),
        n_dominant=st.integers(min_value=1, max_value=2),
        n_other=st.integers(min_value=3, max_value=7),
    )
    @settings(max_examples=200)
    def test_below_60pct_no_opening_warning(self, dominant, n_dominant, n_other):
        """dominant / total < 60% → нет предупреждения."""
        from engine.db_chapters import check_structural_monotony
        assume(n_dominant + n_other >= 4)
        assume(n_dominant + n_other <= 8)
        pct = n_dominant / (n_dominant + n_other)
        assume(pct < 0.6)

        pid = make_project()
        ch = 1
        others = [t for t in ["action", "dialogue", "description", "internal"]
                  if t != dominant]
        for _ in range(n_dominant):
            save_analysis(pid, ch, opening=dominant, closing="")
            ch += 1
        for i in range(n_other):
            save_analysis(pid, ch, opening=others[i % len(others)], closing="")
            ch += 1

        result = check_structural_monotony(pid, before_chapter=ch)
        assert f"«{dominant}»" not in result, (
            f"False positive at {n_dominant}/{n_dominant + n_other} = {pct:.0%}"
        )

    @given(window=st.integers(min_value=100, max_value=1000))
    @settings(max_examples=50)
    def test_large_window_no_crash(self, window):
        """window >> число глав не вызывает crash."""
        from engine.db_chapters import check_structural_monotony
        pid = make_project()
        for ch in range(1, 6):
            save_analysis(pid, ch, opening="action", closing="cliffhanger")
        result = check_structural_monotony(pid, before_chapter=6, window=window)
        assert isinstance(result, str)
        assert "action" in result

    @given(
        opening=opening_types,
        closing=closing_types,
        n=st.integers(min_value=4, max_value=15),
    )
    @settings(max_examples=100)
    def test_idempotent(self, opening, closing, n):
        """Повторный вызов → тот же результат. Нет скрытого state."""
        from engine.db_chapters import check_structural_monotony
        pid = make_project()
        for ch in range(1, n + 1):
            save_analysis(pid, ch, opening, closing)
        r1 = check_structural_monotony(pid, before_chapter=n + 1)
        r2 = check_structural_monotony(pid, before_chapter=n + 1)
        assert r1 == r2


# ==============================================================================
# 4. _trim_modules_to_budget
# ==============================================================================

class TestTrimBudgetProperties:

    @given(
        sizes=st.lists(st.integers(min_value=10, max_value=500),
                       min_size=2, max_size=8),
        budget_pct=st.floats(min_value=0.5, max_value=2.0, allow_nan=False),
    )
    @settings(max_examples=200)
    def test_result_count_equals_input_count(self, sizes, budget_pct):
        """Число модулей в результате == входное. Модули не удаляются."""
        from engine.engine_loaders import _trim_modules_to_budget
        modules = [(f"module_{i:02d}", "X" * s) for i, s in enumerate(sizes)]
        budget = max(1, int(sum(sizes) * budget_pct))
        result = _trim_modules_to_budget(modules, budget)
        assert len(result) == len(modules)

    @given(
        sizes=st.lists(st.integers(min_value=10, max_value=200),
                       min_size=1, max_size=8),
    )
    @settings(max_examples=200)
    def test_no_trim_when_under_budget(self, sizes):
        """total <= budget → результат идентичен входу."""
        from engine.engine_loaders import _trim_modules_to_budget
        modules = [(f"module_{i}", "X" * s) for i, s in enumerate(sizes)]
        result = _trim_modules_to_budget(modules, sum(sizes) + 1)
        assert result == [c for _, c in modules]

    @given(
        sizes=st.lists(st.integers(min_value=10, max_value=200),
                       min_size=2, max_size=8),
    )
    @settings(max_examples=200)
    def test_trimmed_never_longer_than_original(self, sizes):
        """После trim каждый модуль <= оригинального размера."""
        from engine.engine_loaders import _trim_modules_to_budget
        modules = [(f"module_{i:02d}", "X" * s) for i, s in enumerate(sizes)]
        budget = max(1, sum(sizes) // 2)
        result = _trim_modules_to_budget(modules, budget)
        for original, trimmed in zip(sizes, result):
            assert len(trimmed) <= original

    @given(
        content_size=st.integers(min_value=1000, max_value=5000),
        budget_pct=st.floats(min_value=0.05, max_value=0.45, allow_nan=False),
    )
    @settings(max_examples=100)
    def test_documents_budget_not_guaranteed_below_half(self, content_size, budget_pct):
        """
        ДОКУМЕНТИРУЮЩИЙ ТЕСТ: при total > 2x budget бюджет НЕ выполняется.
        Когда дефект исправят — изменить assert на: result_total <= budget.
        """
        from engine.engine_loaders import _trim_modules_to_budget
        assume(budget_pct < 0.5)
        modules = [("05_commercial_heatmap", "X" * content_size)]
        budget = max(1, int(content_size * budget_pct))
        result = _trim_modules_to_budget(modules, budget)
        result_total = sum(len(c) for c in result)
        half = content_size // 2
        if half > budget:
            assert result_total > budget
        else:
            assert result_total <= budget
