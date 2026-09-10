"""
test_chapter_analyzer.py — тесты анализатора глав.

Критические инварианты:
  1. ChapterAnalysis.failed() всегда возвращает analysis_quality='failed'
  2. format_analysis_for_prompt возвращает '' для failed анализа
  3. format_analysis_for_prompt включает logical_gaps
  4. format_analysis_for_prompt включает opened_promises
  5. conflict_score всегда в диапазоне 0.0–1.0
  6. Парсер JSON-ответа LLM не падает на невалидном JSON
"""

import pytest
from unittest.mock import MagicMock, patch


# ─── Тест 1: ChapterAnalysis.failed() ────────────────────────────────────────

def test_failed_sets_quality():
    from engine.chapter_analyzer import ChapterAnalysis
    a = ChapterAnalysis.failed(project_id=1, chapter_num=5)
    assert a.analysis_quality == "failed"
    assert a.project_id == 1
    assert a.chapter_num == 5

def test_failed_has_empty_collections():
    from engine.chapter_analyzer import ChapterAnalysis
    a = ChapterAnalysis.failed(project_id=1, chapter_num=1)
    assert a.opened_promises == []
    assert a.logical_gaps == []
    assert a.arc_progress == {}


# ─── Тест 2: format_analysis_for_prompt ──────────────────────────────────────

def test_format_failed_returns_empty():
    from engine.chapter_analyzer import ChapterAnalysis, format_analysis_for_prompt
    a = ChapterAnalysis.failed(project_id=1, chapter_num=3)
    result = format_analysis_for_prompt(a)
    assert result == "", "format должен вернуть '' для failed анализа"

def test_format_includes_logical_gaps():
    from engine.chapter_analyzer import ChapterAnalysis, format_analysis_for_prompt
    from dataclasses import field
    a = ChapterAnalysis(
        project_id=1, chapter_num=4,
        logical_gaps=["Марина знала код — но ей его никто не давал"],
        conflict_score=0.5,
    )
    result = format_analysis_for_prompt(a)
    assert "Марина" in result or "разрыв" in result.lower()

def test_format_includes_opened_promises():
    from engine.chapter_analyzer import ChapterAnalysis, format_analysis_for_prompt
    a = ChapterAnalysis(
        project_id=1, chapter_num=4,
        opened_promises=["Убийца вернётся в город"],
        conflict_score=0.3,
    )
    result = format_analysis_for_prompt(a)
    assert "Убийца" in result

def test_format_limits_gaps_to_three():
    from engine.chapter_analyzer import ChapterAnalysis, format_analysis_for_prompt
    a = ChapterAnalysis(
        project_id=1, chapter_num=4,
        logical_gaps=[f"разрыв {i}" for i in range(10)],
        conflict_score=0.4,
    )
    result = format_analysis_for_prompt(a)
    # Считаем именно пункты списка: строка-заголовок «Возможные разрывы:»
    # тоже содержит слово «разрыв» и раньше учитывалась как четвёртый пункт
    count = sum(1 for ln in result.splitlines() if ln.strip().startswith("- разрыв"))
    assert count <= 3, f"Ожидалось ≤3 разрывов, нашлось {count}"

def test_format_limits_arcs_to_four():
    from engine.chapter_analyzer import ChapterAnalysis, format_analysis_for_prompt
    a = ChapterAnalysis(
        project_id=1, chapter_num=4,
        arc_progress={f"Персонаж{i}": f"продвинулся {i}" for i in range(10)},
        conflict_score=0.4,
    )
    result = format_analysis_for_prompt(a)
    count = sum(1 for i in range(10) if f"Персонаж{i}" in result)
    assert count <= 4, f"Ожидалось ≤4 арок, нашлось {count}"


# ─── Тест 3: conflict_score диапазон ─────────────────────────────────────────

def test_conflict_score_default_is_zero():
    from engine.chapter_analyzer import ChapterAnalysis
    a = ChapterAnalysis(project_id=1, chapter_num=1)
    assert 0.0 <= a.conflict_score <= 1.0


# ─── Тест 4: to_dict ─────────────────────────────────────────────────────────

def test_to_dict_is_serializable():
    """to_dict() должен возвращать dict без нестандартных типов."""
    from engine.chapter_analyzer import ChapterAnalysis
    import json
    a = ChapterAnalysis(
        project_id=1, chapter_num=2,
        opened_promises=["обещание"],
        logical_gaps=["разрыв"],
        conflict_score=0.7,
        pacing_note="быстрый",
    )
    d = a.to_dict()
    # Не должно бросать. ensure_ascii=False обязателен: иначе кириллица
    # уезжает в \uXXXX и проверка вхождения подстроки всегда ложна.
    serialized = json.dumps(d, ensure_ascii=False)
    assert "обещание" in serialized
    assert "разрыв" in serialized


# ─── Тест 5: ChapterAnalyzer._parse_response ─────────────────────────────

def test_parse_valid_json():
    """Парсер должен корректно обработать валидный JSON."""
    from engine.chapter_analyzer import ChapterAnalyzer
    analyzer = ChapterAnalyzer(
        get_summaries_fn=MagicMock(return_value=[]),
        save_analysis_fn=MagicMock(),
    )
    raw = """{
        "arc_progress": {"Иван": "узнал правду"},
        "opened_promises": ["он вернётся"],
        "closed_promises": [],
        "logical_gaps": [],
        "causal_chains": [],
        "character_deltas": [],
        "conflict_score": 0.7,
        "pacing_note": "быстрый",
        "opening_type": "action",
        "closing_type": "dialogue",
        "plot_threads": {}
    }"""
    result = analyzer._parse_response(raw, project_id=1, chapter_num=3)
    assert result.analysis_quality == "ok"
    assert result.conflict_score == pytest.approx(0.7)
    assert "он вернётся" in result.opened_promises

def test_parse_invalid_json_returns_partial():
    """Невалидный JSON → analysis_quality='partial' или 'failed', не исключение."""
    from engine.chapter_analyzer import ChapterAnalyzer
    analyzer = ChapterAnalyzer(
        get_summaries_fn=MagicMock(return_value=[]),
        save_analysis_fn=MagicMock(),
    )
    result = analyzer._parse_response("{invalid json{{", project_id=1, chapter_num=1)
    assert result.analysis_quality in ("partial", "failed"), (
        f"Ожидалось partial или failed, получено: {result.analysis_quality}"
    )

def test_parse_json_with_markdown_fence():
    """Парсер убирает ```json обёртку."""
    from engine.chapter_analyzer import ChapterAnalyzer
    analyzer = ChapterAnalyzer(
        get_summaries_fn=MagicMock(return_value=[]),
        save_analysis_fn=MagicMock(),
    )
    raw = """```json
    {
        "arc_progress": {},
        "opened_promises": [],
        "closed_promises": [],
        "logical_gaps": ["тест разрыв"],
        "causal_chains": [],
        "character_deltas": [],
        "conflict_score": 0.3,
        "pacing_note": "ровный",
        "opening_type": "description",
        "closing_type": "internal",
        "plot_threads": {}
    }
    ```"""
    result = analyzer._parse_response(raw, project_id=1, chapter_num=2)
    assert result.analysis_quality in ("ok", "partial")
    assert "тест разрыв" in result.logical_gaps

def test_parse_clamps_conflict_score():
    """conflict_score должен быть зажат в [0, 1]."""
    from engine.chapter_analyzer import ChapterAnalyzer
    analyzer = ChapterAnalyzer(
        get_summaries_fn=MagicMock(return_value=[]),
        save_analysis_fn=MagicMock(),
    )
    raw = """{
        "arc_progress": {},
        "opened_promises": [],
        "closed_promises": [],
        "logical_gaps": [],
        "causal_chains": [],
        "character_deltas": [],
        "conflict_score": 5.0,
        "pacing_note": "",
        "opening_type": "",
        "closing_type": "",
        "plot_threads": {}
    }"""
    result = analyzer._parse_response(raw, project_id=1, chapter_num=1)
    assert 0.0 <= result.conflict_score <= 1.0, (
        f"conflict_score={result.conflict_score} выходит за границы [0, 1]"
    )


class TestGetAnalyzer:
    def test_returns_chapter_analyzer_instance(self):
        from engine.chapter_analyzer import get_analyzer, ChapterAnalyzer
        assert isinstance(get_analyzer(), ChapterAnalyzer)

    def test_singleton(self):
        from engine.chapter_analyzer import get_analyzer
        assert get_analyzer() is get_analyzer()
