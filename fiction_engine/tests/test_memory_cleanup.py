"""
Анализ главы, State, L3, анализ серии — разбор формулировок 26.10, пакет 27.10:
поля, которые никто не читал, и сбои, которые проходили молча.
"""
import json

GLOBAL = ("## ПЕРСОНАЖИ\n\n### Иван\nСОСТОЯНИЕ: устал\nЛОКАЦИЯ: лес\nЗНАЕТ: []\nНЕ_ЗНАЕТ: []\n\n"
          "### Марина\nСОСТОЯНИЕ: спокойна\nЗНАЕТ: []\n")


def _state(project_id):
    from engine.db_state import update_state
    update_state(project_id, global_state=GLOBAL, plot_matrix="СТАТУС: активна\n", memory_graph="")


# ─── State: знание героя — одно поле на оба раздела ──────────────────────────

def test_knows_goes_to_card_and_memory(project_id):
    """memory_changes.knows пишется и в ЗНАЕТ карточки (её видит писатель), и в
    «кто что знает» — в том числе у героя без других перемен."""
    from engine.db_state import get_state, merge_analysis_into_state
    _state(project_id)
    merge_analysis_into_state(project_id, json.dumps({
        "global_state_changes": [{"name": "Иван", "локация": "замок"}],
        "memory_changes": [{"name": "Иван", "knows": ["меч у кузнеца"]},
                           {"name": "Марина", "knows": ["Иван солгал"]}]}, ensure_ascii=False), 2)
    s = get_state(project_id)
    g = s["global_state"]
    assert "меч у кузнеца" in g and "Иван солгал" in g and "ЛОКАЦИЯ: замок" in g
    assert "меч у кузнеца" in s["memory_graph"] and "Иван солгал" in s["memory_graph"]


def test_old_analysis_with_both_fields_not_doubled(project_id):
    """Анализ, сохранённый до 27.10, — с «узнал» и knows: в карточку один раз."""
    from engine.db_state import get_state, merge_analysis_into_state
    _state(project_id)
    merge_analysis_into_state(project_id, json.dumps({
        "global_state_changes": [{"name": "Иван", "узнал": "меч у кузнеца"}],
        "memory_changes": [{"name": "Иван", "knows": ["меч у кузнеца"]}]}, ensure_ascii=False), 2)
    assert get_state(project_id)["global_state"].count("меч у кузнеца") == 1


# ─── State свободным текстом — без модели ────────────────────────────────────

def test_free_state_goes_to_writer_without_model():
    """Разбор свободного State моделью убран: видел 2000 символов State, досочинял
    запреты, без «@» рвался на 200 токенах. Свободный текст идёт писателю как есть."""
    import inspect

    from engine.pipeline_context import extract_relevant_state
    assert "api_call_fn" not in inspect.signature(extract_relevant_state).parameters
    free = {"global_state": "Лукаш — фельдшер, после катастрофы не спит.", "plot_matrix": "", "memory_graph": ""}
    assert "не спит" in extract_relevant_state(free, "Глава 2. Лукаш")


# ─── Анализ главы: старые сохранённые анализы ────────────────────────────────

def test_old_saved_analysis_still_loads():
    """Анализ черновика, сохранённый в запуске до 27.10, — с полями, которых больше
    нет: «Принять» берёт его, а не зовёт модель заново."""
    from engine.chapter_analyzer import ChapterAnalysis
    a = ChapterAnalysis.from_dict({"project_id": 1, "chapter_num": 3, "pacing_note": "ровный",
                                   "character_deltas": [{"name": "Иван"}], "closed_promises": [],
                                   "plot_threads": {"поиск": "активна"}, "analysis_quality": "ok"})
    assert a.pacing_note == "ровный" and not hasattr(a, "plot_threads")


def test_analysis_prompt_asks_only_read_fields():
    from engine.chapter_analyzer import _ANALYSIS_PROMPT
    for gone in ("character_deltas", "closed_promises", "plot_threads", "Потенциальный"):
        assert gone not in _ANALYSIS_PROMPT


# ─── L3 ──────────────────────────────────────────────────────────────────────

def test_l3_sample_has_no_constant_fields():
    """resolved и resolved_chapter ставит normalize_promises — модель их не переписывает."""
    from engine.l3_memory import SUMMARY_PROMPT
    assert "resolved" not in SUMMARY_PROMPT


# ─── Анализ серии: обещания по номеру, сбой — виден ──────────────────────────

def _nil(summaries):
    from engine.narrative_intelligence import NarrativeIntelligence
    return NarrativeIntelligence(get_summaries_fn=lambda *a, **k: summaries,
                                 get_state_fn=lambda *a, **k: {},
                                 get_chapters_fn=lambda *a, **k: [])


SUMMARIES = [
    {"chapter_num": 1, "events": "Иван нашёл письмо", "promises": [
        {"id": "1_0", "text": "Кто написал письмо Ивану"}]},
    {"chapter_num": 12, "events": "Марина призналась, что письмо написала она", "promises": []},
]


def test_promise_resolution_by_number():
    seen = []

    def call(prompt):
        seen.append(prompt)
        if '"resolutions"' in prompt:
            return '{"resolutions": [{"n": 1, "resolved": true, "chapter": 12}]}'
        if '"contradictions"' in prompt:
            return '{"contradictions": []}'
        return '{"arcs": []}'
    report = _nil(SUMMARIES).analyze(1, 12, call)
    prompt = next(p for p in seen if '"resolutions"' in p)
    assert "1. Гл.1: Кто написал письмо Ивану" in prompt
    item = report.promise_status[0]
    assert item["resolved"] is True and item["resolved_chapter"] == 12


def test_promise_check_failure_is_reported_not_overdue():
    """Ответ не разобран — не «ни одно не выполнено»: просрочки нет, автору — сбой."""
    def call(prompt):
        if '"contradictions"' in prompt:
            return '{"contradictions": []}'
        if '"arcs"' in prompt:
            return '{"arcs": []}'
        return '{"resolutions": [{"n": 1, "resol'      # оборван потолком
    report = _nil(SUMMARIES).analyze(1, 12, call)
    assert report.promise_status[0]["overdue"] is False
    assert any("обещаний не прошла" in w for w in report.warnings)


def test_narrative_caller_gets_its_budget(monkeypatch):
    from engine import pipeline
    from engine.narrative_intelligence import NARRATIVE_MAX_TOKENS
    seen = {}

    def fake_caller(model_value, max_tokens=400):
        seen["max_tokens"] = max_tokens
        return lambda prompt: "{}"
    monkeypatch.setattr(pipeline, "_make_model_caller", fake_caller)
    monkeypatch.setattr("engine.narrative_intelligence.analyze_narrative", lambda *a: None)
    pipeline.run_narrative_analysis(1, 3, "m")
    assert seen["max_tokens"] == NARRATIVE_MAX_TOKENS > 400


# ─── Предпроверка: план главы и без поля ok ──────────────────────────────────

def test_prevalidation_gets_plan(project_id, monkeypatch):
    from engine import prevalidation
    from engine.db import save_director_note
    save_director_note(project_id, 0, "СЦЕНА 1: Причал\n  Вера встречает следователя")
    seen = {}

    def fake_call(model, system, user, **kw):
        seen["user"] = user
        return '{"blocking": [], "warnings": []}'
    monkeypatch.setattr(prevalidation, "call_model", fake_call)
    monkeypatch.setattr(prevalidation, "_check_state_contradictions", lambda *a, **k: [])
    prevalidation.prevalidate_chapter(project_id, 1, "Вера ищет улики", "m")
    assert "ПЛАН ГЛАВЫ 1:" in seen["user"] and "Причал" in seen["user"]
    assert '"ok"' not in prevalidation.VALIDATION_PROMPT
    assert "диалектик" not in prevalidation.VALIDATION_PROMPT


# ─── Импорт в State: разметка, которую читает разбор ─────────────────────────

def test_state_import_format_matches_parser():
    from engine.db_core import STATE_IMPORT_FORMAT
    for key in ("### Имя", "СОСТОЯНИЕ:", "ЦЕЛЬ_СЕЙЧАС:", "## КТО ЧТО ЗНАЕТ", "ГДЕ_СЕЙЧАС"):
        assert key in STATE_IMPORT_FORMAT
    assert "КЛЮЧЕВЫЕ СОБЫТИЯ" not in STATE_IMPORT_FORMAT
