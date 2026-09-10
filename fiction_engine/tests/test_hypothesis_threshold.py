"""
test_hypothesis_threshold.py — property-based тесты для get_project_accept_threshold.

Зачем hypothesis вместо ручных случаев:
  Медиана и bias — нетривиальная математика на реальных данных.
  Ручные тесты проверяют конкретные числа; hypothesis генерирует тысячи комбинаций
  и находит граничные случаи которые человек не придумает:
  float precision, все одинаковые, один элемент, очень большие числа.

Инварианты которые должны держаться при любых входных данных:
  1. threshold ∈ [min(scores), max(scores)]
  2. threshold — медиана: ровно половина scores ≤ threshold и ≥ threshold
  3. judge_bias = round(avg - median, 1)
  4. accepted_count == len(scores)
  5. При n < min_accepted → всегда None
  6. При n >= min_accepted → всегда не None

Установка:
    pip install hypothesis

Запуск:
    pytest tests/test_hypothesis_threshold.py -v
    # или с подробным выводом:
    pytest tests/test_hypothesis_threshold.py -v --hypothesis-show-statistics
"""

import sys
import pathlib
import tempfile
from unittest.mock import MagicMock, patch

# ─── Моки до импорта engine ───────────────────────────────────────────────────
sys.modules.setdefault("openai", MagicMock())
sys.modules.setdefault("anthropic", MagicMock())
if not hasattr(sys.modules["openai"], "OpenAI"):
    sys.modules["openai"].OpenAI = MagicMock()

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pytest

try:
    from hypothesis import given, settings, assume
    from hypothesis import strategies as st
    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False

skip_if_no_hypothesis = pytest.mark.skipif(
    not HYPOTHESIS_AVAILABLE,
    reason="hypothesis не установлен: pip install hypothesis"
)


# ─── Вспомогательные функции ──────────────────────────────────────────────────

def _reference_median(scores: list[float]) -> float:
    """Эталонная реализация медианы для сравнения с кодом."""
    s = sorted(scores)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _reference_bias(scores: list[float], median: float) -> float:
    avg = sum(scores) / len(scores)
    return round(avg - median, 1)


def _setup_db_with_scores(scores: list[float]) -> tuple[int, pathlib.Path]:
    """Создать временную БД с принятыми главами по списку scores."""
    tmp = pathlib.Path(tempfile.mkdtemp()) / "test.db"
    from engine.db_core import init_db, get_conn
    init_db()
    from engine.db_projects import create_project
    pid = create_project("Hypothesis проект", "фэнтези")
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
    return pid, tmp


# ─── Property-based тесты ─────────────────────────────────────────────────────

@skip_if_no_hypothesis
class TestThresholdProperties:

    @given(
        scores=st.lists(
            st.floats(min_value=0.0, max_value=50.0,
                      allow_nan=False, allow_infinity=False),
            min_size=5, max_size=20
        )
    )
    @settings(max_examples=300)
    def test_threshold_within_score_range(self, scores):
        """
        Инвариант: threshold ∈ [min(scores), max(scores)].
        Медиана не может быть за пределами набора данных.
        """
        tmp = pathlib.Path(tempfile.mkdtemp()) / "test.db"
        with patch("engine.db_core.DB_PATH", tmp):
            pid, _ = _setup_db_with_scores(scores)
            from engine.db_chapters import get_project_accept_threshold
            result = get_project_accept_threshold(pid, min_accepted=5)

        assert result is not None
        # threshold округляется до 0.1 (это значение уходит в подсказку судье),
        # поэтому на границе диапазона допустима погрешность в половину шага:
        # round(0.25, 1) = 0.2 формально ниже min(scores)=0.25.
        eps = 0.05
        assert min(scores) - eps <= result["threshold"] <= max(scores) + eps, (
            f"threshold={result['threshold']} вне диапазона "
            f"[{min(scores)}, {max(scores)}] для scores={sorted(scores)}"
        )

    @given(
        scores=st.lists(
            st.floats(min_value=0.0, max_value=50.0,
                      allow_nan=False, allow_infinity=False),
            min_size=5, max_size=20
        )
    )
    @settings(max_examples=300)
    def test_threshold_matches_reference_median(self, scores):
        """
        Инвариант: threshold совпадает с эталонной медианой.
        Проверяем что реализация не имеет off-by-one ошибок.
        """
        tmp = pathlib.Path(tempfile.mkdtemp()) / "test.db"
        with patch("engine.db_core.DB_PATH", tmp):
            pid, _ = _setup_db_with_scores(scores)
            from engine.db_chapters import get_project_accept_threshold
            result = get_project_accept_threshold(pid, min_accepted=5)

        # Сравниваем с эталоном, округлённым так же, как в коде:
        # реализация возвращает round(median, 1) осознанно.
        expected = round(_reference_median(scores), 1)
        assert result["threshold"] == pytest.approx(expected, abs=0.01), (
            f"threshold={result['threshold']} != expected={expected} "
            f"для sorted scores={sorted(scores)}"
        )

    @given(
        scores=st.lists(
            st.floats(min_value=0.0, max_value=50.0,
                      allow_nan=False, allow_infinity=False),
            min_size=5, max_size=20
        )
    )
    @settings(max_examples=300)
    def test_bias_matches_reference(self, scores):
        """
        Инвариант: judge_bias = round(avg - median, 1).
        Проверяем расчёт bias независимо от медианы.
        """
        tmp = pathlib.Path(tempfile.mkdtemp()) / "test.db"
        with patch("engine.db_core.DB_PATH", tmp):
            pid, _ = _setup_db_with_scores(scores)
            from engine.db_chapters import get_project_accept_threshold
            result = get_project_accept_threshold(pid, min_accepted=5)

        median = _reference_median(scores)
        expected_bias = _reference_bias(scores, median)
        assert result["judge_bias"] == pytest.approx(expected_bias, abs=0.05), (
            f"bias={result['judge_bias']} != expected={expected_bias}"
        )

    @given(
        scores=st.lists(
            st.floats(min_value=0.0, max_value=50.0,
                      allow_nan=False, allow_infinity=False),
            min_size=5, max_size=20
        )
    )
    @settings(max_examples=300)
    def test_accepted_count_matches_input(self, scores):
        """
        Инвариант: accepted_count == len(scores).
        Функция не теряет записи и не дублирует их.
        """
        tmp = pathlib.Path(tempfile.mkdtemp()) / "test.db"
        with patch("engine.db_core.DB_PATH", tmp):
            pid, _ = _setup_db_with_scores(scores)
            from engine.db_chapters import get_project_accept_threshold
            result = get_project_accept_threshold(pid, min_accepted=5)

        # Функция берёт LIMIT 20, поэтому при len > 20 считаем 20
        expected_count = min(len(scores), 20)
        assert result["accepted_count"] == expected_count, (
            f"accepted_count={result['accepted_count']} != {expected_count}"
        )

    @given(
        n=st.integers(min_value=0, max_value=4),
        scores=st.lists(
            st.floats(min_value=0.0, max_value=50.0,
                      allow_nan=False, allow_infinity=False),
            min_size=0, max_size=4
        )
    )
    @settings(max_examples=200)
    def test_below_min_accepted_always_none(self, n, scores):
        """
        Инвариант: при len(scores) < min_accepted → всегда None.
        Независимо от конкретных значений.
        """
        assume(len(scores) < 5)
        tmp = pathlib.Path(tempfile.mkdtemp()) / "test.db"
        with patch("engine.db_core.DB_PATH", tmp):
            pid, _ = _setup_db_with_scores(scores)
            from engine.db_chapters import get_project_accept_threshold
            result = get_project_accept_threshold(pid, min_accepted=5)

        assert result is None, (
            f"Ожидали None при {len(scores)} записях < min_accepted=5, "
            f"получили {result}"
        )

    @given(
        scores=st.lists(
            st.just(42.0),  # все одинаковые
            min_size=5, max_size=10
        )
    )
    @settings(max_examples=50)
    def test_all_equal_scores(self, scores):
        """
        Граничный случай: все scores одинаковые.
        threshold == score, bias == 0.0.
        """
        tmp = pathlib.Path(tempfile.mkdtemp()) / "test.db"
        with patch("engine.db_core.DB_PATH", tmp):
            pid, _ = _setup_db_with_scores(scores)
            from engine.db_chapters import get_project_accept_threshold
            result = get_project_accept_threshold(pid, min_accepted=5)

        assert result["threshold"] == pytest.approx(42.0)
        assert result["judge_bias"] == pytest.approx(0.0, abs=0.1)

    @given(
        scores=st.lists(
            st.floats(min_value=0.0, max_value=50.0,
                      allow_nan=False, allow_infinity=False),
            min_size=5, max_size=20
        )
    )
    @settings(max_examples=200)
    def test_format_hint_always_returns_string(self, scores):
        """
        Инвариант: format_project_threshold_hint всегда возвращает str,
        никогда не None и не бросает исключений.
        """
        tmp = pathlib.Path(tempfile.mkdtemp()) / "test.db"
        with patch("engine.db_core.DB_PATH", tmp):
            pid, _ = _setup_db_with_scores(scores)
            from engine.db_chapters import get_project_accept_threshold, format_project_threshold_hint
            data = get_project_accept_threshold(pid, min_accepted=5)
            hint = format_project_threshold_hint(data)

        assert isinstance(hint, str), f"hint должен быть str, получили {type(hint)}"

    @given(
        threshold=st.floats(min_value=0.0, max_value=50.0,
                            allow_nan=False, allow_infinity=False),
        bias=st.floats(min_value=-20.0, max_value=20.0,
                       allow_nan=False, allow_infinity=False),
        count=st.integers(min_value=5, max_value=50)
    )
    @settings(max_examples=300)
    def test_format_hint_accept_floor_invariant(self, threshold, bias, count):
        """
        Инвариант: accept_floor = max(threshold - 3, 30.0) ≥ 30.
        Никогда не должно быть число меньше 30 в подсказке как accept_floor.
        """
        from engine.db_chapters import format_project_threshold_hint
        data = {"threshold": threshold, "judge_bias": bias, "accepted_count": count}
        hint = format_project_threshold_hint(data)

        # accept_floor рассчитывается как max(t - 3.0, 30.0)
        expected_floor = max(threshold - 3.0, 30.0)
        floor_str = f"{expected_floor:.0f}"
        assert floor_str in hint, (
            f"accept_floor={expected_floor} не найден в hint для threshold={threshold}"
        )


# ─── Детерминированные тесты (не требуют hypothesis) ─────────────────────────
# Эти тесты дублируют несколько граничных случаев из hypothesis
# но работают без установленного пакета.

class TestThresholdDeterministic:
    """Ключевые граничные случаи без hypothesis."""

    def _insert(self, scores):
        from engine.db_projects import create_project
        from engine.db_core import get_conn
        pid = create_project("Det проект", "фэнтези")
        with get_conn() as conn:
            for ch, score in enumerate(scores, start=1):
                conn.execute("""INSERT INTO pipeline_runs
                    (project_id,chapter_num,status,model_gen,model_critic,model_editor,model_judge)
                    VALUES (?,?,'accepted','m','m','m','m')""",(pid,ch))
                rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                conn.execute("""INSERT INTO pipeline_iterations
                    (run_id,iteration,stage,model_used,input_text,output_text,score)
                    VALUES (?,1,'judge','m','','',?)""",(rid,score))
        return pid

    def test_single_score_value_50(self, project_id):
        # Граничный: score = 50 (максимум)
        tmp_pid = self._insert([50.0, 50.0, 50.0, 50.0, 50.0])
        from engine.db_chapters import get_project_accept_threshold
        r = get_project_accept_threshold(tmp_pid, min_accepted=5)
        assert r["threshold"] == pytest.approx(50.0)
        assert r["judge_bias"] == pytest.approx(0.0, abs=0.1)

    def test_single_score_value_0(self, project_id):
        # Граничный: score = 0 (минимум)
        tmp_pid = self._insert([0.0, 0.0, 0.0, 0.0, 0.0])
        from engine.db_chapters import get_project_accept_threshold
        r = get_project_accept_threshold(tmp_pid, min_accepted=5)
        assert r["threshold"] == pytest.approx(0.0)

    def test_large_spread(self, project_id):
        # [0, 0, 25, 50, 50] → median=25, avg=25, bias=0
        tmp_pid = self._insert([0.0, 0.0, 25.0, 50.0, 50.0])
        from engine.db_chapters import get_project_accept_threshold
        r = get_project_accept_threshold(tmp_pid, min_accepted=5)
        assert r["threshold"] == pytest.approx(25.0)
        assert r["judge_bias"] == pytest.approx(0.0, abs=0.1)

    def test_threshold_always_ge_30_in_format_hint(self, project_id):
        # threshold=5 → accept_floor = max(5-3, 30) = 30
        from engine.db_chapters import format_project_threshold_hint
        hint = format_project_threshold_hint({"threshold": 5.0, "judge_bias": 0.0, "accepted_count": 5})
        assert "30" in hint
        assert "2" not in hint.split("≥")[1][:5]  # не "2" после ≥
