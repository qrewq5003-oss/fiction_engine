"""
test_narrative_intelligence.py — тесты Narrative Intelligence Layer (NIL).

Покрываемые инварианты:

  Метрики (без LLM):
    1.  _conflict_word_score: диапазон 0.1–1.0, растёт при наличии слов
    2.  _pacing_to_urgency: известные слова → правильный urgency, пустая строка → default + data_available=False
    3.  _tension_score: диапазон 0.0–1.0
    4.  _mood_polarity: pos / neg / neutral
    5.  _warn_tension_pattern: три пика → предупреждение; ровно → предупреждение; < 3 глав → []
    6.  _count_mood_shifts: нейтральные главы не ломают подсчёт полярных разворотов

  NarrativeIntelligence (юнит, без БД):
    7.  get_metrics: возвращает dict с нужными ключами, значения в диапазонах
    8.  get_promise_status: только raw-промисы, без LLM
    9.  analyze: без саммари → NarrativeReport с предупреждением, ok=True
    10. analyze: с саммари → LLM вызывается ровно N раз, отчёт непустой
    11. analyze: LLM падает → исключение не выбрасывается, возвращается report
    12. _extract_raw_promises: пропускает «нет», «—», короткие строки
    13. _extract_raw_promises: разбивает по «;» и «\n»
    14. analyze: БЛОКИРУЮЩЕЕ противоречие → ok=False
    15. analyze: warnings содержит _warn_tension_pattern если три пика подряд
    16. _warn_tension_pattern: жанровые цели используются корректно
"""

import pytest
from unittest.mock import MagicMock, patch


# ─── Хелперы ─────────────────────────────────────────────────────────────────

def _make_summary(chapter_num: int, conflicts: str = "", mood: str = "",
                  promises: str = "", events: str = "", characters: str = "",
                  project_id: int = 1) -> dict:
    return {
        "chapter_num":  chapter_num,
        "project_id":   project_id,
        "conflicts":    conflicts,
        "mood":         mood,
        "promises":     promises,
        "events":       events,
        "characters":   characters,
    }


def _make_nil(summaries: list, chapters_fn=None):
    """NarrativeIntelligence с инъектированными заглушками (без БД)."""
    from engine.narrative_intelligence import NarrativeIntelligence
    return NarrativeIntelligence(
        get_summaries_fn=MagicMock(return_value=summaries),
        get_state_fn=MagicMock(return_value=None),
        get_chapters_fn=chapters_fn or MagicMock(return_value=[]),
    )


# ─── 1. _conflict_word_score ──────────────────────────────────────────────────

def test_conflict_word_score_minimum():
    from engine.narrative_intelligence import _conflict_word_score
    score = _conflict_word_score("")
    assert score == pytest.approx(0.1), "Пустой текст → минимум 0.1"

def test_conflict_word_score_grows_with_words():
    from engine.narrative_intelligence import _conflict_word_score
    low  = _conflict_word_score("спокойная прогулка по парку")
    high = _conflict_word_score("конфликт угроза смерть предательство опасность кризис")
    assert high > low

def test_conflict_word_score_capped_at_one():
    from engine.narrative_intelligence import _conflict_word_score
    # Все слова из списка
    text = " ".join(["конфликт", "угроза", "смерть", "предательство",
                     "опасность", "кризис", "атак", "схватк",
                     "раскрыт", "ложь", "перелом", "открылось"])
    assert _conflict_word_score(text) <= 1.0

def test_conflict_word_score_range():
    from engine.narrative_intelligence import _conflict_word_score
    for text in ["", "конфликт", "всё спокойно"]:
        s = _conflict_word_score(text)
        assert 0.1 <= s <= 1.0, f"score={s} вне диапазона для '{text}'"


# ─── 2. _pacing_to_urgency ────────────────────────────────────────────────────

@pytest.mark.parametrize("pacing,expected_urgency,expected_data", [
    ("быстрый",     0.75, True),
    ("медленный",   0.20, True),
    ("нарастающий", 0.60, True),
    ("ровный",      0.40, True),
    ("лирический",  0.15, True),
    ("",            0.40, False),   # пустая строка → default, данных нет
    ("   ",         0.40, False),   # только пробелы
    ("неизвестно",  0.40, True),    # не распознано, но данные были
])
def test_pacing_to_urgency(pacing, expected_urgency, expected_data):
    from engine.narrative_intelligence import _pacing_to_urgency
    urgency, data_ok = _pacing_to_urgency(pacing)
    assert urgency  == pytest.approx(expected_urgency), f"pacing='{pacing}'"
    assert data_ok  == expected_data,                   f"pacing='{pacing}'"


# ─── 3. _tension_score ───────────────────────────────────────────────────────

def test_tension_score_range():
    from engine.narrative_intelligence import _tension_score
    combos = [
        ("конфликт смерть", "быстрый",   "мрачное"),
        ("тихо",            "медленный", "светлое"),
        ("",                "",          ""),
    ]
    for conflicts, pacing, mood in combos:
        s = _tension_score(conflicts, pacing, mood)
        assert 0.0 <= s <= 1.0, f"score={s} для ({conflicts!r}, {pacing!r}, {mood!r})"

def test_tension_score_high_conflict_raises_score():
    from engine.narrative_intelligence import _tension_score
    low  = _tension_score("прогулка", "медленный", "спокойное")
    high = _tension_score("конфликт угроза смерть", "быстрый", "мрачное")
    assert high > low


# ─── 4. _mood_polarity ───────────────────────────────────────────────────────

@pytest.mark.parametrize("mood,expected", [
    ("светлое утро",    "pos"),
    ("мрачное небо",    "neg"),
    ("нейтральный тон", "neutral"),
    ("радостное",       "pos"),
    ("ужас и отчаяние", "neg"),
    ("",                "neutral"),
])
def test_mood_polarity(mood, expected):
    from engine.narrative_intelligence import _mood_polarity
    assert _mood_polarity(mood) == expected


# ─── 5. _warn_tension_pattern ────────────────────────────────────────────────

def test_warn_tension_pattern_empty_for_short_series():
    from engine.narrative_intelligence import _warn_tension_pattern
    assert _warn_tension_pattern([0.8, 0.9]) == []

def test_warn_tension_pattern_three_peaks():
    from engine.narrative_intelligence import _warn_tension_pattern
    # Три пика подряд для жанра по умолчанию (peak=0.75)
    scores   = [0.3, 0.4, 0.8, 0.85, 0.9]
    warnings = _warn_tension_pattern(scores)
    assert any("пик" in w.lower() or "подряд" in w.lower() for w in warnings), \
        f"Ожидалось предупреждение о пиках, получено: {warnings}"

def test_warn_tension_pattern_flat():
    from engine.narrative_intelligence import _warn_tension_pattern
    # Пять совершенно одинаковых значений — ровно
    scores   = [0.5, 0.5, 0.5, 0.5, 0.5]
    warnings = _warn_tension_pattern(scores)
    assert any("ровн" in w.lower() for w in warnings), \
        f"Ожидалось предупреждение о ровном напряжении, получено: {warnings}"

def test_warn_tension_pattern_low_conflict_drought():
    from engine.narrative_intelligence import _warn_tension_pattern
    scores   = [0.5, 0.1, 0.15, 0.2]
    warnings = _warn_tension_pattern(scores)
    assert any("низк" in w.lower() or "конфликт" in w.lower() for w in warnings), \
        f"Ожидалось предупреждение о засухе конфликта, получено: {warnings}"

def test_warn_tension_pattern_genre_calibration():
    from engine.narrative_intelligence import _warn_tension_pattern
    # romance: avg_target=0.35, peak=0.65
    # При среднем 0.7 должно сработать «выше нормы жанра»
    scores   = [0.7, 0.72, 0.68, 0.71, 0.69]
    warnings = _warn_tension_pattern(scores, genre_family="romance")
    assert any("норм" in w.lower() or "выше" in w.lower() for w in warnings), \
        f"Ожидалось жанровое предупреждение для romance, получено: {warnings}"

def test_warn_tension_pattern_multiple_warnings_not_exclusive():
    """Предупреждения не взаимоисключающие — могут сработать несколько."""
    from engine.narrative_intelligence import _warn_tension_pattern
    # Три пика + ровный (все одинаково высокие) + выше нормы жанра для romance
    scores   = [0.8, 0.82, 0.81, 0.83, 0.80]
    warnings = _warn_tension_pattern(scores, genre_family="romance")
    assert len(warnings) >= 2, \
        f"Ожидалось ≥2 предупреждений, получено {len(warnings)}: {warnings}"


# ─── 6. _count_mood_shifts ───────────────────────────────────────────────────

def test_count_mood_shifts_neutral_bridge():
    """pos → neutral → neg должно считаться как 1 разворот, а не 0."""
    nil = _make_nil([])
    summaries = [
        _make_summary(1, mood="светлое"),   # pos
        _make_summary(2, mood="нейтральный"),  # neutral — мост
        _make_summary(3, mood="мрачное"),   # neg
    ]
    shifts = nil._count_mood_shifts(summaries)
    assert shifts == 1, f"Ожидался 1 разворот через neutral, получено {shifts}"

def test_count_mood_shifts_no_neutral():
    nil = _make_nil([])
    summaries = [
        _make_summary(1, mood="светлое"),
        _make_summary(2, mood="мрачное"),
        _make_summary(3, mood="светлое"),
    ]
    assert nil._count_mood_shifts(summaries) == 2

def test_count_mood_shifts_all_neutral():
    nil = _make_nil([])
    summaries = [_make_summary(i, mood="нейтральный") for i in range(5)]
    assert nil._count_mood_shifts(summaries) == 0

def test_count_mood_shifts_empty():
    nil = _make_nil([])
    assert nil._count_mood_shifts([]) == 0


# ─── 7. get_metrics ──────────────────────────────────────────────────────────

def test_get_metrics_returns_required_keys():
    summaries = [
        _make_summary(1, conflicts="конфликт", mood="мрачное"),
        _make_summary(2, conflicts="угроза",   mood="светлое"),
        _make_summary(3, conflicts="смерть",   mood="тревожное"),
    ]
    nil     = _make_nil(summaries)
    metrics = nil.get_metrics(project_id=1, through_chapter=3)

    required = {"chapters_analyzed", "mood_trajectory", "conflict_density",
                "pacing_coverage", "promise_count", "avg_conflict_score",
                "mood_shift_count"}
    assert required <= metrics.keys(), \
        f"Отсутствуют ключи: {required - metrics.keys()}"

def test_get_metrics_chapters_analyzed():
    summaries = [_make_summary(i, conflicts="конфликт") for i in range(1, 6)]
    nil       = _make_nil(summaries)
    metrics   = nil.get_metrics(project_id=1, through_chapter=5)
    assert metrics["chapters_analyzed"] == 5

def test_get_metrics_conflict_density_length_matches_summaries():
    summaries = [_make_summary(i) for i in range(1, 4)]
    nil       = _make_nil(summaries)
    metrics   = nil.get_metrics(project_id=1, through_chapter=3)
    assert len(metrics["conflict_density"]) == 3

def test_get_metrics_avg_conflict_score_in_range():
    summaries = [_make_summary(i, conflicts="конфликт угроза") for i in range(1, 4)]
    nil       = _make_nil(summaries)
    metrics   = nil.get_metrics(project_id=1, through_chapter=3)
    assert 0.0 <= metrics["avg_conflict_score"] <= 1.0

def test_get_metrics_pacing_coverage_in_range():
    summaries = [_make_summary(i) for i in range(1, 4)]
    nil       = _make_nil(summaries)
    metrics   = nil.get_metrics(project_id=1, through_chapter=3)
    assert 0.0 <= metrics["pacing_coverage"] <= 1.0


# ─── 8. get_promise_status ───────────────────────────────────────────────────

def test_get_promise_status_no_llm():
    """get_promise_status не должен вызывать LLM."""
    summaries = [
        _make_summary(1, promises="Убийца вернётся"),
        _make_summary(2, promises="нет"),
        _make_summary(3, promises="Тайна раскроется; Герой найдёт меч"),
    ]
    nil    = _make_nil(summaries)
    result = nil.get_promise_status(project_id=1, through_chapter=3)
    assert len(result) == 3  # 1 + 0 + 2
    texts = [r["promise"] for r in result]
    assert any("Убийца" in t for t in texts)
    assert any("Тайна"  in t for t in texts)
    assert any("Герой"  in t for t in texts)


# ─── 9. _extract_raw_promises ────────────────────────────────────────────────

def test_extract_raw_promises_skips_empty_and_nope():
    nil = _make_nil([])
    summaries = [
        _make_summary(1, promises="нет"),
        _make_summary(2, promises="—"),
        _make_summary(3, promises="-"),
        _make_summary(4, promises=""),
        _make_summary(5, promises="Нет"),
    ]
    assert nil._extract_raw_promises(summaries) == []

def test_extract_raw_promises_splits_semicolon():
    nil = _make_nil([])
    summaries = [_make_summary(1, promises="Первое обещание; Второе обещание")]
    result = nil._extract_raw_promises(summaries)
    assert len(result) == 2

def test_extract_raw_promises_splits_newline():
    nil = _make_nil([])
    summaries = [_make_summary(1, promises="Первое обещание\nВторое обещание")]
    result = nil._extract_raw_promises(summaries)
    assert len(result) == 2

def test_extract_raw_promises_skips_short():
    """Строки короче 10 символов после trim пропускаются."""
    nil = _make_nil([])
    summaries = [_make_summary(1, promises="ok; нормальное обещание о чём-то важном")]
    result = nil._extract_raw_promises(summaries)
    texts = [t for _, t in result]
    assert not any(len(t) <= 10 for t in texts)

def test_extract_raw_promises_chapter_num_preserved():
    nil = _make_nil([])
    summaries = [_make_summary(7, promises="Герой вернётся в деревню")]
    result = nil._extract_raw_promises(summaries)
    assert result[0][0] == 7


# ─── 10. analyze: без саммари ────────────────────────────────────────────────

def test_analyze_empty_summaries_returns_report_with_warning():
    nil    = _make_nil([])
    report = nil.analyze(project_id=1, through_chapter=5,
                         api_call_fn=MagicMock())
    assert report.ok is True
    assert len(report.warnings) >= 1
    assert any("саммари" in w.lower() for w in report.warnings)

def test_analyze_empty_summaries_no_llm_calls():
    llm = MagicMock()
    nil = _make_nil([])
    nil.analyze(project_id=1, through_chapter=5, api_call_fn=llm)
    llm.assert_not_called()


# ─── 11. analyze: с саммари — LLM вызывается, отчёт непустой ─────────────────

def _arc_response():
    return '{"arcs": [{"character": "Иван", "status": "active", "evolution": "растёт", "stalled": false, "last_chapter": 3}]}'

def _promise_response():
    return '{"resolutions": [{"promise": "Убийца вернётся в город", "resolved": false, "chapter": null}]}'

def _contradiction_response():
    return '{"contradictions": []}'

def test_analyze_with_summaries_calls_llm():
    summaries = [
        _make_summary(1, conflicts="конфликт", mood="мрачное",
                      promises="Убийца вернётся в город",
                      events="Иван вошёл в замок", characters="Иван"),
        _make_summary(2, conflicts="угроза",   mood="тревожное",
                      events="Иван нашёл улику", characters="Иван"),
        _make_summary(3, conflicts="смерть",   mood="ужас",
                      events="Финальная схватка", characters="Иван"),
    ]
    responses = [_arc_response(), _promise_response(), _contradiction_response()]
    llm = MagicMock(side_effect=responses)
    nil = _make_nil(summaries)

    report = nil.analyze(project_id=1, through_chapter=3, api_call_fn=llm)

    assert llm.call_count >= 2, "Ожидалось минимум 2 LLM-вызова"
    assert report.project_id     == 1
    assert report.through_chapter == 3

def test_analyze_with_summaries_report_structure():
    summaries = [_make_summary(i, conflicts="конфликт", mood="мрачное",
                               events="событие", characters="Иван")
                 for i in range(1, 4)]
    llm = MagicMock(side_effect=[_arc_response(), _promise_response(),
                                  _contradiction_response()])
    nil = _make_nil(summaries)

    report = nil.analyze(project_id=1, through_chapter=3, api_call_fn=llm)

    assert isinstance(report.warnings,          list)
    assert isinstance(report.mood_trajectory,   list)
    assert isinstance(report.conflict_density,  list)
    assert isinstance(report.arc_health,        dict)
    assert isinstance(report.promise_status,    list)
    assert isinstance(report.contradictions,    list)
    assert len(report.conflict_density) == 3

def test_analyze_mood_trajectory_populated():
    summaries = [
        _make_summary(1, mood="светлое"),
        _make_summary(2, mood="мрачное"),
    ]
    llm = MagicMock(side_effect=[_arc_response(), _promise_response(),
                                  _contradiction_response()])
    nil = _make_nil(summaries)

    report = nil.analyze(project_id=1, through_chapter=2, api_call_fn=llm)

    assert len(report.mood_trajectory) == 2
    assert any("светлое" in m for m in report.mood_trajectory)
    assert any("мрачное" in m for m in report.mood_trajectory)


# ─── 12. analyze: LLM падает — нет исключений ────────────────────────────────

def test_analyze_llm_raises_no_exception_propagated():
    """Если LLM бросает исключение — analyze не должен его пробрасывать."""
    summaries = [_make_summary(i, conflicts="конфликт", mood="мрачное",
                               events="событие", characters="Иван")
                 for i in range(1, 4)]
    llm = MagicMock(side_effect=RuntimeError("API недоступен"))
    nil = _make_nil(summaries)

    # Не должно бросать
    report = nil.analyze(project_id=1, through_chapter=3, api_call_fn=llm)
    assert report is not None
    assert report.project_id == 1

def test_analyze_llm_returns_invalid_json_no_exception():
    """Невалидный JSON от LLM — analyze возвращает отчёт, не падает."""
    summaries = [_make_summary(i, conflicts="конфликт", mood="мрачное",
                               events="событие", characters="Иван")
                 for i in range(1, 4)]
    llm = MagicMock(return_value="{invalid json{{")
    nil = _make_nil(summaries)

    report = nil.analyze(project_id=1, through_chapter=3, api_call_fn=llm)
    assert report is not None


# ─── 13. analyze: БЛОКИРУЮЩЕЕ противоречие → ok=False ───────────────────────

def test_analyze_blocking_contradiction_sets_ok_false():
    summaries = [_make_summary(i, conflicts="конфликт", mood="мрачное",
                               events="событие", characters="Иван")
                 for i in range(1, 4)]

    blocking_response = '{"contradictions": [{"chapters": [1, 3], "description": "Иван мёртв в гл.1 но жив в гл.3", "severity": "blocking"}]}'
    llm = MagicMock(side_effect=[_arc_response(), _promise_response(),
                                  blocking_response])
    nil = _make_nil(summaries)

    report = nil.analyze(project_id=1, through_chapter=3, api_call_fn=llm)

    assert report.ok is False
    assert any("БЛОКИРУЮЩЕЕ" in c for c in report.contradictions)

def test_analyze_no_contradictions_ok_true():
    summaries = [_make_summary(i, conflicts="конфликт", mood="мрачное",
                               events="событие", characters="Иван")
                 for i in range(1, 4)]
    llm = MagicMock(side_effect=[_arc_response(), _promise_response(),
                                  _contradiction_response()])
    nil = _make_nil(summaries)

    report = nil.analyze(project_id=1, through_chapter=3, api_call_fn=llm)
    assert report.ok is True


# ─── 14. analyze: warnings содержит tension-предупреждение при трёх пиках ────

def test_analyze_generates_tension_warning_for_three_peaks():
    """Три главы подряд с высоким конфликтом → tension warning в report."""
    # Много конфликтных слов → высокий tension score
    high_conflict = "конфликт угроза смерть предательство опасность кризис"
    summaries = [
        _make_summary(i, conflicts=high_conflict, mood="мрачное", events="событие")
        for i in range(1, 4)
    ]
    llm = MagicMock(side_effect=[_arc_response(), _promise_response(),
                                  _contradiction_response()])
    nil = _make_nil(summaries)

    report = nil.analyze(project_id=1, through_chapter=3, api_call_fn=llm)

    tension_warnings = [w for w in report.warnings
                        if "пик" in w.lower() or "напряжен" in w.lower()
                        or "три" in w.lower()]
    assert len(tension_warnings) >= 1, \
        f"Ожидалось предупреждение о напряжении, warnings={report.warnings}"


# ─── 15. Фильтрация саммари по through_chapter ───────────────────────────────

def test_analyze_filters_summaries_above_through_chapter():
    """Саммари с chapter_num > through_chapter не должны учитываться."""
    summaries_all = [_make_summary(i) for i in range(1, 8)]  # главы 1-7
    get_summaries = MagicMock(return_value=summaries_all)

    from engine.narrative_intelligence import NarrativeIntelligence
    nil = NarrativeIntelligence(
        get_summaries_fn=get_summaries,
        get_state_fn=MagicMock(return_value=None),
        get_chapters_fn=MagicMock(return_value=[]),
    )

    llm = MagicMock(side_effect=[_arc_response(), _promise_response(),
                                  _contradiction_response()])
    report = nil.analyze(project_id=1, through_chapter=3, api_call_fn=llm)

    # conflict_density должна быть только для глав 1-3
    assert len(report.conflict_density) == 3


# ─── 16. _extract_conflict_density: pacing_coverage ─────────────────────────

def test_extract_conflict_density_no_project_id_graceful():
    """Если project_id отсутствует в саммари — не падает, pacing_coverage=0."""
    nil = _make_nil([])
    summaries = [
        {"chapter_num": 1, "conflicts": "конфликт", "mood": "мрачное"},
        {"chapter_num": 2, "conflicts": "угроза",   "mood": "тревожное"},
    ]
    scores, coverage = nil._extract_conflict_density(summaries)
    assert len(scores) == 2
    assert 0.0 <= coverage <= 1.0
