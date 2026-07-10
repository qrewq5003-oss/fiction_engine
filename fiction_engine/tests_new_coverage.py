# -*- coding: utf-8 -*-
"""
tests_new_coverage.py — тесты непокрытых функций (peak_finales, director_note,
unified_engine, cognitive_memory, pipeline_steps, pipeline integration).

Запускается через run_tests.py (run() определён там) или как standalone
с помощью встроенного runner'а ниже.
"""

import sys, os, tempfile, pathlib, unittest.mock as _mock
from pathlib import Path
from unittest.mock import MagicMock, patch

# Мок внешних зависимостей
for _mod in ["openai", "anthropic"]:
    sys.modules.setdefault(_mod, MagicMock())
sys.modules["openai"].OpenAI = MagicMock()

# ─── Runner (standalone) ─────────────────────────────────────────────────────
_passed = 0
_failed = 0
_errors = []

def run(name, fn):
    global _passed, _failed
    try:
        fn()
        print(f"  ✓ {name}")
        _passed += 1
    except Exception as e:
        print(f"  ✗ {name}: {type(e).__name__}: {e}")
        _failed += 1
        _errors.append((name, str(e)))

def make_db():
    import importlib
    tmp = tempfile.mkdtemp()
    db_file = Path(tmp) / "test.db"
    for mod in ["engine.db_core", "engine.error_policy", "engine.logger",
                "engine.db_settings", "engine.db_projects", "engine.db_state",
                "engine.db_chapters", "engine.db_narrative", "engine.db",
                "engine.l3_memory", "engine.continuity_checker",
                "engine.cognitive_memory", "engine.prevalidation"]:
        if mod in sys.modules:
            sys.modules.pop(mod)
    import engine.db_core as _dbc
    _dbc.DB_PATH = db_file
    from engine.db_core import init_db
    init_db()
    return db_file


# ════════════════════════════════════════════════════════
print("\n══ peak_finales ══")
# ════════════════════════════════════════════════════════

from engine.peak_finales import PEAK_FINALES, get_peak_finale, get_all_sources

def test_pf_required_fields():
    required = {"technique", "principle", "example", "breakdown"}
    for source, data in PEAK_FINALES.items():
        missing = required - set(data.keys())
        assert missing == set(), f"{source}: нет полей {missing}"
run("peak_finales: все записи имеют обязательные поля", test_pf_required_fields)

def test_pf_no_empty_fields():
    for source, data in PEAK_FINALES.items():
        for field in ("technique", "principle", "example", "breakdown"):
            assert data[field].strip(), f"{source}.{field} пустое"
run("peak_finales: ни одно поле не пустое", test_pf_no_empty_fields)

def test_pf_example_length():
    for source, data in PEAK_FINALES.items():
        assert len(data["example"].strip()) > 50, f"{source}.example слишком короткий"
run("peak_finales: все примеры длиннее 50 символов", test_pf_example_length)

def test_pf_get_known():
    sources = list(PEAK_FINALES.keys())
    if sources:
        result = get_peak_finale(sources[0])
        assert isinstance(result, str) and len(result) > 10
run("peak_finales: get_peak_finale известный источник -> строка", test_pf_get_known)

def test_pf_get_unknown():
    assert get_peak_finale("nonexistent_xyz_author") is None
run("peak_finales: get_peak_finale неизвестный -> None", test_pf_get_unknown)

def test_pf_get_all_sources():
    sources = get_all_sources()
    assert isinstance(sources, list)
    assert len(sources) == len(PEAK_FINALES)
    assert all(isinstance(s, str) for s in sources)
run("peak_finales: get_all_sources возвращает все ключи", test_pf_get_all_sources)


# ════════════════════════════════════════════════════════
print("\n══ director_note ══")
# ════════════════════════════════════════════════════════

import unittest.mock as _mock
from engine.director_note import generate_director_note

def test_dn_saves_and_returns():
    saved = []
    with _mock.patch("engine.director_note.save_director_note",
                     side_effect=lambda pid, ch, note: saved.append(note)):
        result = generate_director_note(
            project_id=1, chapter_num=5,
            chapter_text="Текст главы. " * 50,
            state={"global_state": "Мир тёмный."},
            api_call_fn=lambda p: "Не торопить реакцию. Тишина важнее.",
        )
    assert result == "Не торопить реакцию. Тишина важнее."
    assert saved == ["Не торопить реакцию. Тишина важнее."]
run("director_note: сохраняет и возвращает заметку", test_dn_saves_and_returns)

def test_dn_empty_response_returns_none():
    saved = []
    with _mock.patch("engine.director_note.save_director_note",
                     side_effect=lambda pid, ch, note: saved.append(note)):
        result = generate_director_note(
            project_id=1, chapter_num=5,
            chapter_text="Текст " * 50,
            state={},
            api_call_fn=lambda p: "",
        )
    assert result is None
    assert saved == []
run("director_note: пустой ответ -> None, не сохраняет", test_dn_empty_response_returns_none)

def test_dn_short_response_returns_none():
    with _mock.patch("engine.director_note.save_director_note"):
        result = generate_director_note(
            project_id=1, chapter_num=1,
            chapter_text="Текст " * 50,
            state={},
            api_call_fn=lambda p: "ок",  # < 10 символов
        )
    assert result is None
run("director_note: ответ < 10 символов -> None", test_dn_short_response_returns_none)

def test_dn_api_raises_returns_none():
    result = generate_director_note(
        project_id=1, chapter_num=1,
        chapter_text="Текст " * 50,
        state={},
        api_call_fn=lambda p: (_ for _ in ()).throw(RuntimeError("down")),
    )
    assert result is None
run("director_note: api raises -> None (не crash)", test_dn_api_raises_returns_none)

def test_dn_uses_chapter_tail():
    """Промпт содержит хвост главы."""
    prompts = []
    unique_tail = "УНИКАЛЬНЫЙ_ХВОСТ_ГЛАВЫ_XYZ"
    chapter_text = "начало " * 200 + unique_tail
    with _mock.patch("engine.director_note.save_director_note"):
        generate_director_note(
            project_id=1, chapter_num=1,
            chapter_text=chapter_text,
            state={"global_state": ""},
            api_call_fn=lambda p: (prompts.append(p), "Заметка здесь.")[1],
        )
    assert prompts and unique_tail in prompts[0]
run("director_note: промпт содержит хвост главы", test_dn_uses_chapter_tail)


# ════════════════════════════════════════════════════════
print("\n══ unified_engine: _select_modules / _trim_char_profile / _append_if ══")
# ════════════════════════════════════════════════════════

from engine.unified_engine import (
    _select_modules, _trim_char_profile, _append_if,
    resolve_modules_dynamic, get_active_modules,
)
from engine.engine_config import MODE_MODULES

def test_ue_select_pre_selected_no_llm():
    called = [False]
    result = _select_modules(
        "quick", "fantasy", ["01_tension_curve"], "",
        lambda p: (called.__setitem__(0, True), "")[1],
    )
    assert "01_tension_curve" in result
    assert not called[0]
run("unified_engine: _select_modules pre_selected -> без LLM", test_ue_select_pre_selected_no_llm)

def test_ue_select_static_fallback():
    result = _select_modules("quick", None, None, "", None)
    assert isinstance(result, list) and len(result) > 0
run("unified_engine: _select_modules quick/None -> статический список", test_ue_select_static_fallback)

def test_ue_select_genre_adds_modules():
    base   = _select_modules("quality", None, None, "", None)
    with_g = _select_modules("quality", "detective", None, "", None)
    assert len(with_g) >= len(base)
run("unified_engine: _select_modules с жанром >= без жанра", test_ue_select_genre_adds_modules)

def test_ue_trim_char_profile_short():
    p = "Короткий профиль."
    assert _trim_char_profile(p, max_chars=1000) == p
run("unified_engine: _trim_char_profile короткий -> без изменений", test_ue_trim_char_profile_short)

def test_ue_trim_char_profile_long():
    p = "Строка.\n" * 200
    result = _trim_char_profile(p, max_chars=50)
    assert len(result) < len(p)
run("unified_engine: _trim_char_profile длинный -> обрезается", test_ue_trim_char_profile_long)

def test_ue_append_if_nonempty():
    sections = []
    _append_if(sections, "k", "контент")
    assert sections == [("k", "контент")]
run("unified_engine: _append_if добавляет непустой контент", test_ue_append_if_nonempty)

def test_ue_append_if_empty_skipped():
    sections = []
    _append_if(sections, "k", "")
    assert sections == []
run("unified_engine: _append_if пропускает пустую строку", test_ue_append_if_empty_skipped)

def test_ue_resolve_modules_dynamic_valid():
    import json as _j
    resp = _j.dumps(["01_tension_curve", "15_dialogue_style"])
    result = resolve_modules_dynamic("напряжение и диалог", "detective", lambda p: resp)
    assert "01_tension_curve" in result
    assert "07_voice_consistency" in result  # BASE_MODULE
run("unified_engine: resolve_modules_dynamic валидный JSON", test_ue_resolve_modules_dynamic_valid)

def test_ue_resolve_modules_dynamic_invalid_json():
    result = resolve_modules_dynamic("задача", "fantasy", lambda p: "не JSON")
    assert isinstance(result, list) and len(result) > 0
run("unified_engine: resolve_modules_dynamic невалидный JSON -> fallback", test_ue_resolve_modules_dynamic_invalid_json)

def test_ue_resolve_modules_dynamic_filters_unknown():
    import json as _j
    resp = _j.dumps(["01_tension_curve", "99_nonexistent_module_xyz"])
    result = resolve_modules_dynamic("задача", None, lambda p: resp)
    assert "99_nonexistent_module_xyz" not in result
    assert "01_tension_curve" in result
run("unified_engine: resolve_modules_dynamic фильтрует неизвестные модули", test_ue_resolve_modules_dynamic_filters_unknown)

def test_ue_resolve_modules_dynamic_llm_raises():
    result = resolve_modules_dynamic(
        "задача", None,
        lambda p: (_ for _ in ()).throw(RuntimeError("API down")),
    )
    assert isinstance(result, list)
run("unified_engine: resolve_modules_dynamic LLM raises -> fallback", test_ue_resolve_modules_dynamic_llm_raises)

def test_ue_get_active_modules_returns_list():
    result = get_active_modules("фэнтези", "quick")
    assert isinstance(result, list) and len(result) > 0
run("unified_engine: get_active_modules -> непустой список", test_ue_get_active_modules_returns_list)

def test_ue_get_active_modules_master_gte_quick():
    q = get_active_modules("детектив", "quick")
    m = get_active_modules("детектив", "master")
    assert len(m) >= len(q)
run("unified_engine: master >= quick по числу модулей", test_ue_get_active_modules_master_gte_quick)

def test_ue_build_engine_context_no_engine():
    """Без движка -> пустая строка."""
    with _mock.patch("engine.unified_engine.engine_available", return_value=False):
        from engine.unified_engine import build_engine_context
        result = build_engine_context("фэнтези", "quick")
    assert result == ""
run("unified_engine: build_engine_context без движка -> ''", test_ue_build_engine_context_no_engine)


# ════════════════════════════════════════════════════════
print("\n══ cognitive_memory: полное покрытие ══")
# ════════════════════════════════════════════════════════

from engine.cognitive_memory import (
    get_cognitive_context, get_weighted_promises,
    _select_inclusions, _format_cognitive_context,
    memory_score_report, MEMORY_FIELDS,
)

def _s(chapter_num, events="", promises="", characters="", conflicts="", mood=""):
    return {
        "chapter_num": chapter_num,
        "events": events, "promises": promises,
        "characters": characters, "conflicts": conflicts, "mood": mood,
    }

def test_cog_no_summaries():
    with _mock.patch("engine.cognitive_memory.get_l3_summaries", return_value=[]):
        assert get_cognitive_context(1, before_chapter=5) == ""
run("cognitive_memory: нет саммари -> пустая строка", test_cog_no_summaries)

def test_cog_one_summary_contains_chapter():
    with _mock.patch("engine.cognitive_memory.get_l3_summaries",
                     return_value=[_s(1, events="Герой встретил злодея")]):
        result = get_cognitive_context(1, before_chapter=3)
    assert "Глава 1" in result
run("cognitive_memory: одно саммари -> содержит номер главы", test_cog_one_summary_contains_chapter)

def test_cog_promises_always_included():
    summaries = [_s(1, promises="Тайна шкатулки"), _s(2, events="Встреча")]
    with _mock.patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
        result = get_cognitive_context(1, before_chapter=5)
    assert "Тайна шкатулки" in result
run("cognitive_memory: promises из старых глав включаются", test_cog_promises_always_included)

def test_cog_select_inclusions_recent_all_fields():
    by_ch = {1: _s(1, events="событие", promises="обещание")}
    inc = _select_inclusions(by_ch, [1], [1], latest_chapter=1, max_chapters=5)
    assert "events" in inc[1]
    assert "promises" in inc[1]
run("cognitive_memory: _select_inclusions recent -> все непустые поля", test_cog_select_inclusions_recent_all_fields)

def test_cog_select_inclusions_promises_from_old():
    by_ch = {1: _s(1, promises="старое"), 5: _s(5, events="новое")}
    inc = _select_inclusions(by_ch, [1, 5], [5], latest_chapter=5, max_chapters=5)
    assert "promises" in inc[1]
run("cognitive_memory: _select_inclusions promises из нерецентных глав", test_cog_select_inclusions_promises_from_old)

def test_cog_format_structure():
    by_ch = {1: _s(1, events="встреча"), 2: _s(2, events="битва")}
    inc = {1: {"events"}, 2: {"events"}}
    result = _format_cognitive_context(by_ch, [1, 2], [2], inc, latest_chapter=2)
    assert "КОГНИТИВНАЯ ПАМЯТЬ" in result
    assert "Глава 1" in result
    assert "Глава 2" in result
run("cognitive_memory: _format_cognitive_context структура", test_cog_format_structure)

def test_cog_format_recent_marker():
    by_ch = {1: _s(1, events="старое"), 3: _s(3, events="новое")}
    inc = {1: {"events"}, 3: {"events"}}
    result = _format_cognitive_context(by_ch, [1, 3], [3], inc, latest_chapter=3)
    assert "★" in result
    assert "·" in result
run("cognitive_memory: ★ рецентные, · старые", test_cog_format_recent_marker)

def test_cog_weighted_promises_no_data():
    with _mock.patch("engine.cognitive_memory.get_l3_summaries", return_value=[]):
        result = get_weighted_promises(1, before_chapter=5)
    assert result == ""
run("cognitive_memory: get_weighted_promises нет данных -> ''", test_cog_weighted_promises_no_data)

def test_cog_weighted_promises_returns_content():
    summaries = [_s(1, promises="Герой вернётся"), _s(2, promises="Предатель будет разоблачён")]
    with _mock.patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
        result = get_weighted_promises(1, before_chapter=5)
    assert "Герой вернётся" in result or "Предатель" in result
run("cognitive_memory: get_weighted_promises -> содержит обещания", test_cog_weighted_promises_returns_content)

def test_cog_memory_score_report_no_crash():
    with _mock.patch("engine.cognitive_memory.get_l3_summaries", return_value=[]):
        result = memory_score_report(1, before_chapter=5)
    assert isinstance(result, str)
run("cognitive_memory: memory_score_report нет данных -> строка без crash", test_cog_memory_score_report_no_crash)


# ════════════════════════════════════════════════════════
print("\n══ pipeline_steps: step_generate / step_drift_check / step_chapter_analysis ══")
# ════════════════════════════════════════════════════════

from engine.pipeline_steps import step_generate, step_drift_check, step_chapter_analysis

def test_sg_writes_results():
    results = {}
    with _mock.patch("engine.pipeline_steps.save_pipeline_iteration"):
        step_generate(
            run_id=1, iteration=1, chapter_num=5,
            generation_prompt="Задача",
            full_prompt="Полный промпт",
            model_gen="model::x",
            sys_generator="Ты писатель.",
            call_fn=lambda m, s, p, **kw: "Сгенерированный текст.",
            results=results,
        )
    assert results["generated_text"] == "Сгенерированный текст."
    assert results["stage"] == "generate"
run("pipeline_steps: step_generate пишет generated_text и stage", test_sg_writes_results)

def test_sg_saves_iteration():
    saved = []
    results = {}
    with _mock.patch("engine.pipeline_steps.save_pipeline_iteration",
                     side_effect=lambda *a, **kw: saved.append(1)):
        step_generate(1, 1, 5, "задача", "промпт", "m::x", "sys",
                      lambda m, s, p, **kw: "текст", results)
    assert len(saved) == 1
run("pipeline_steps: step_generate вызывает save_pipeline_iteration", test_sg_saves_iteration)

def test_sdc_skips_when_not_needed():
    called = [False]
    results = {}
    with _mock.patch("engine.pipeline_steps.should_check_drift", return_value=False):
        step_drift_check(1, 5, "текст", "m::x",
                         lambda m, s, p, **kw: (called.__setitem__(0, True), "")[1],
                         results)
    assert not called[0] and "drift_warning" not in results
run("pipeline_steps: step_drift_check пропускает если не нужен", test_sdc_skips_when_not_needed)

def test_sdc_fills_warning():
    results = {}
    with _mock.patch("engine.pipeline_steps.should_check_drift", return_value=True):
        with _mock.patch("engine.pipeline_steps.check_voice_drift",
                         return_value={"warning": "Голос изменился", "score": 5.5}):
            step_drift_check(1, 5, "текст", "m::x", lambda *a, **kw: "", results)
    assert results.get("drift_warning") == "Голос изменился"
    assert results.get("drift_score") == 5.5
run("pipeline_steps: step_drift_check заполняет drift_warning", test_sdc_fills_warning)

def test_sdc_error_recoverable():
    results = {}
    with _mock.patch("engine.pipeline_steps.should_check_drift",
                     side_effect=RuntimeError("DB error")):
        step_drift_check(1, 5, "текст", "m::x", lambda *a, **kw: "", results)
    # Не должно бросать — тест прошёл
run("pipeline_steps: step_drift_check ошибка -> RECOVERABLE", test_sdc_error_recoverable)

def test_sca_fills_results():
    from engine.chapter_analyzer import ChapterAnalysis
    results = {}
    analysis = ChapterAnalysis(
        project_id=1, chapter_num=5,
        logical_gaps=["Марина не могла знать"],
        opened_promises=["Тайна шкатулки"],
        arc_progress={"Анна": "продвинулась"},
        analysis_quality="ok",
    )
    with _mock.patch("engine.pipeline_steps.analyze_chapter_deep", return_value=analysis):
        with _mock.patch("engine.pipeline_steps.queue_state_update_from_analysis"):
            step_chapter_analysis(1, 5, "Текст главы. " * 30, "m::x",
                                  lambda m, s, p: "", results)
    assert "chapter_analysis_block" in results or "logical_gaps" in results
run("pipeline_steps: step_chapter_analysis заполняет results", test_sca_fills_results)

def test_sca_failed_no_block():
    from engine.chapter_analyzer import ChapterAnalysis
    results = {}
    with _mock.patch("engine.pipeline_steps.analyze_chapter_deep",
                     return_value=ChapterAnalysis.failed(1, 5)):
        with _mock.patch("engine.pipeline_steps.queue_state_update_from_analysis"):
            step_chapter_analysis(1, 5, "Текст. " * 30, "m::x",
                                  lambda m, s, p: "", results)
    assert "chapter_analysis_block" not in results
run("pipeline_steps: step_chapter_analysis failed -> нет chapter_analysis_block", test_sca_failed_no_block)

def test_sca_error_recoverable():
    results = {}
    with _mock.patch("engine.pipeline_steps.analyze_chapter_deep",
                     side_effect=RuntimeError("LLM down")):
        with _mock.patch("engine.pipeline_steps.handle_error"):
            step_chapter_analysis(1, 5, "Текст. " * 30, "m::x",
                                  lambda m, s, p: "", results)
    # Не crash — тест прошёл
run("pipeline_steps: step_chapter_analysis ошибка -> RECOVERABLE", test_sca_error_recoverable)


# ════════════════════════════════════════════════════════
print("\n══ pipeline: _execute_steps / call_json / score_text ══")
# ════════════════════════════════════════════════════════

import tempfile, pathlib
from engine.pipeline import _execute_steps, PipelineStep, call_json, score_text

def _make_tmp_db():
    tmp = tempfile.mkdtemp()
    return pathlib.Path(tmp) / "test.db"

def test_exec_generate_only():
    db = _make_tmp_db()
    with _mock.patch("engine.db_core.DB_PATH", db):
        from engine.db_core import init_db; init_db()
        from engine.db_projects import create_project
        pid = create_project("Тест", "фэнтези")

        results = {}
        with _mock.patch("engine.pipeline.save_pipeline_iteration"):
            with _mock.patch("engine.pipeline._build_context", return_value="ctx"):
                with _mock.patch("engine.pipeline.step_drift_check"):
                    with _mock.patch("engine.pipeline.step_chapter_analysis"):
                        results = _execute_steps(
                            steps=[PipelineStep("generate")],
                            run_id=1, iteration=1,
                            project_id=pid, chapter_num=1,
                            generation_prompt="Задача",
                            model_gen="m::x", model_critic="m::x",
                            model_editor="m::x", model_judge="m::x",
                        )
    # step_generate не вызывается напрямую — _execute_steps вызывает _call через step_generate
    # Достаточно проверить что results имеет iteration
    assert results.get("iteration") == 1
run("pipeline: _execute_steps generate -> iteration в results", test_exec_generate_only)

def test_exec_disabled_step_skipped():
    db = _make_tmp_db()
    with _mock.patch("engine.db_core.DB_PATH", db):
        from engine.db_core import init_db; init_db()
        from engine.db_projects import create_project
        pid = create_project("Тест", "фэнтези")

        judge_called = [False]
        with _mock.patch("engine.pipeline.save_pipeline_iteration"):
            with _mock.patch("engine.pipeline._build_context", return_value="ctx"):
                with _mock.patch("engine.pipeline.step_drift_check"):
                    with _mock.patch("engine.pipeline.step_chapter_analysis"):
                        with _mock.patch("engine.pipeline.step_judge",
                                         side_effect=lambda *a, **kw: judge_called.__setitem__(0, True)):
                            _execute_steps(
                                steps=[PipelineStep("generate"), PipelineStep("judge", enabled=False)],
                                run_id=1, iteration=1,
                                project_id=pid, chapter_num=1,
                                generation_prompt="Задача",
                                model_gen="m::x", model_critic="m::x",
                                model_editor="m::x", model_judge="m::x",
                            )
    assert not judge_called[0]
run("pipeline: _execute_steps disabled шаг не вызывается", test_exec_disabled_step_skipped)

def test_exec_critique_score():
    db = _make_tmp_db()
    critique_resp = "ГОЛОС: 8 СТРУКТУРА: 7 ПЕРСОНАЖИ: 8 СЦЕНЫ: 9 ДИАЛОГ: 8\nИТОГ: 40"
    with _mock.patch("engine.db_core.DB_PATH", db):
        from engine.db_core import init_db; init_db()
        from engine.db_projects import create_project
        pid = create_project("Тест", "детектив")

        with _mock.patch("engine.pipeline.save_pipeline_iteration"):
            with _mock.patch("engine.pipeline._call", return_value=critique_resp):
                with _mock.patch("engine.pipeline.get_all_logical_gaps", return_value=[]):
                    with _mock.patch("engine.pipeline.handle_error"):
                        result = _execute_steps(
                            steps=[PipelineStep("critique")],
                            run_id=1, iteration=1,
                            project_id=pid, chapter_num=3,
                            generation_prompt="Задача",
                            model_gen="m::x", model_critic="m::x",
                            model_editor="m::x", model_judge="m::x",
                        )
    assert result.get("critic_score") == 40.0
run("pipeline: _execute_steps critique -> critic_score", test_exec_critique_score)

def test_exec_judge_verdict():
    db = _make_tmp_db()
    judge_resp = "ИТОГ: 42\nВЕРДИКТ: ПРИНЯТЬ\nОБОСНОВАНИЕ: Хорошо."
    with _mock.patch("engine.db_core.DB_PATH", db):
        from engine.db_core import init_db; init_db()
        from engine.db_projects import create_project
        pid = create_project("Тест", "хоррор")

        with _mock.patch("engine.pipeline.save_pipeline_iteration"):
            with _mock.patch("engine.pipeline._call", return_value=judge_resp):
                with _mock.patch("engine.pipeline.handle_error"):
                    result = _execute_steps(
                        steps=[PipelineStep("judge")],
                        run_id=1, iteration=1,
                        project_id=pid, chapter_num=5,
                        generation_prompt="Задача",
                        model_gen="m::x", model_critic="m::x",
                        model_editor="m::x", model_judge="m::x",
                    )
    assert result.get("verdict") == "ПРИНЯТЬ"
    assert result.get("judge_score") == 42.0
run("pipeline: _execute_steps judge -> verdict и judge_score", test_exec_judge_verdict)

def test_call_json_valid():
    import json as _j
    with _mock.patch("engine.pipeline._call", return_value=_j.dumps({"key": "val"})):
        result = call_json("m::x", "sys", "prompt")
    assert result["key"] == "val"
run("pipeline: call_json валидный JSON", test_call_json_valid)

def test_call_json_embedded():
    with _mock.patch("engine.pipeline._call", return_value='Текст {"ok": true} конец'):
        result = call_json("m::x", "sys", "prompt")
    assert result["ok"] is True
run("pipeline: call_json JSON внутри текста", test_call_json_embedded)

def test_call_json_no_json_raises():
    with _mock.patch("engine.pipeline._call", return_value="нет JSON здесь"):
        try:
            call_json("m::x", "sys", "prompt")
            assert False, "должен ValueError"
        except ValueError:
            pass
run("pipeline: call_json нет JSON -> ValueError", test_call_json_no_json_raises)

def test_score_text_returns_total():
    import json as _j
    resp = _j.dumps({
        "literary_quality": 7, "voice_genre": 8,
        "commercial": 6, "scene_health": 7,
        "total": 7.0, "verdict": "Норм", "main_issue": "Темп",
    })
    with _mock.patch("engine.pipeline._call", return_value=resp):
        result = score_text("Текст.", "фэнтези", "m::x")
    assert "total" in result and isinstance(result["total"], float)
run("pipeline: score_text возвращает dict с total", test_score_text_returns_total)

def test_score_text_computes_missing_total():
    import json as _j
    resp = _j.dumps({
        "literary_quality": 8, "voice_genre": 8,
        "commercial": 8, "scene_health": 8,
    })
    with _mock.patch("engine.pipeline._call", return_value=resp):
        result = score_text("Текст.", "детектив", "m::x")
    assert result.get("total") == 8.0
run("pipeline: score_text вычисляет total если отсутствует", test_score_text_computes_missing_total)


# ════════════════════════════════════════════════════════
print("\n══ pipeline: start_pipeline / continue_pipeline ══")
# ════════════════════════════════════════════════════════

from engine.pipeline import start_pipeline, continue_pipeline
from engine.pipeline_config import AUTO_IMPROVE, STANDARD

def _setup_db():
    db = _make_tmp_db()
    from unittest.mock import patch as _p
    return db

def test_start_pipeline_returns_run_id():
    db = _make_tmp_db()
    judge_resp = "ИТОГ: 42\nВЕРДИКТ: ПРИНЯТЬ\nОБОСНОВАНИЕ: Ок."
    with _mock.patch("engine.db_core.DB_PATH", db):
        from engine.db_core import init_db; init_db()
        from engine.db_projects import create_project
        pid = create_project("Тест", "фэнтези")

        with _mock.patch("engine.pipeline._call", return_value=judge_resp):
            with _mock.patch("engine.pipeline.step_generate",
                             side_effect=lambda *a, **kw: kw["results"].__setitem__("generated_text", "Текст." * 30)):
                with _mock.patch("engine.pipeline.step_drift_check"):
                    with _mock.patch("engine.pipeline.step_chapter_analysis"):
                        with _mock.patch("engine.pipeline._build_context", return_value="ctx"):
                            result = start_pipeline(
                                project_id=pid, chapter_num=1,
                                generation_prompt="Задача",
                                model_gen="m::x", model_critic="m::x",
                                model_editor="m::x", model_judge="m::x",
                            )
    assert "run_id" in result and isinstance(result["run_id"], int)
run("pipeline: start_pipeline возвращает run_id", test_start_pipeline_returns_run_id)

def test_start_pipeline_auto_retry_stops_on_degradation():
    """Реальный авто-ретрай: score упал -> цикл прерывается."""
    db = _make_tmp_db()
    responses = iter([
        "ИТОГ: 30\nВЕРДИКТ: НА ДОРАБОТКУ\nОБОСНОВАНИЕ: плохо",
        "ИТОГ: 25\nВЕРДИКТ: НА ДОРАБОТКУ\nОБОСНОВАНИЕ: хуже",
        "ИТОГ: 40\nВЕРДИКТ: ПРИНЯТЬ\nОБОСНОВАНИЕ: ок",  # не должно дойти
    ])
    with _mock.patch("engine.db_core.DB_PATH", db):
        from engine.db_core import init_db; init_db()
        from engine.db_projects import create_project
        pid = create_project("Тест", "фэнтези")

        with _mock.patch("engine.pipeline._call", side_effect=lambda *a, **kw: next(responses)):
            with _mock.patch("engine.pipeline.step_generate",
                             side_effect=lambda *a, **kw: kw["results"].__setitem__("generated_text", "T" * 30)):
                with _mock.patch("engine.pipeline.step_drift_check"):
                    with _mock.patch("engine.pipeline.step_chapter_analysis"):
                        with _mock.patch("engine.pipeline._build_context", return_value="ctx"):
                            result = start_pipeline(
                                project_id=pid, chapter_num=1,
                                generation_prompt="Задача",
                                model_gen="m::x", model_critic="m::x",
                                model_editor="m::x", model_judge="m::x",
                                config=AUTO_IMPROVE,
                            )
    assert result.get("verdict") == "НА ДОРАБОТКУ"
    assert result.get("judge_score") == 25.0
run("pipeline: start_pipeline авто-ретрай останавливается при деградации score", test_start_pipeline_auto_retry_stops_on_degradation)

def test_continue_pipeline_returns_run_id():
    db = _make_tmp_db()
    judge_resp = "ИТОГ: 44\nВЕРДИКТ: ПРИНЯТЬ\nОБОСНОВАНИЕ: Отлично."
    with _mock.patch("engine.db_core.DB_PATH", db):
        from engine.db_core import init_db; init_db()
        from engine.db_projects import create_project
        from engine.db import create_pipeline_run
        pid = create_project("Тест", "детектив")
        run_id = create_pipeline_run(pid, 1, "m::x", "m::x", "m::x", "m::x")

        with _mock.patch("engine.pipeline._call", return_value=judge_resp):
            with _mock.patch("engine.pipeline._build_context", return_value="ctx"):
                with _mock.patch("engine.pipeline.handle_error"):
                    result = continue_pipeline(
                        run_id=run_id,
                        project_id=pid, chapter_num=1,
                        generation_prompt="Задача",
                        previous_text="Предыдущий текст.",
                        previous_critique="Критика.",
                    )
    assert "run_id" in result and result["run_id"] == run_id
run("pipeline: continue_pipeline возвращает run_id", test_continue_pipeline_returns_run_id)


# ─── Итог (standalone) ───────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n{'━'*50}")
    total = _passed + _failed
    print(f"Итого: {_passed}/{total} прошли", end="")
    if _failed:
        print(f"  |  {_failed} провалено")
        for name, err in _errors:
            print(f"  ✗ {name}: {err}")
    else:
        print("  ✓ Все тесты зелёные")
    sys.exit(0 if _failed == 0 else 1)
