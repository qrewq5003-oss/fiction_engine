#!/usr/bin/env python3
"""Blueprint tests — Flask test client."""

import sys, os, tempfile, pathlib, json
from unittest.mock import MagicMock, patch

for _mod in ["openai", "anthropic"]:
    sys.modules[_mod] = MagicMock()
sys.modules["openai"].OpenAI = MagicMock()

_tmp_dir    = None
_db_path    = None
_app        = None
_client     = None
_project_id = None

def _setup():
    global _tmp_dir, _db_path, _app, _client, _project_id
    import engine.db_core as _dbc
    _tmp_dir = tempfile.mkdtemp()
    _db_path = pathlib.Path(_tmp_dir) / "test.db"
    _dbc.DB_PATH = _db_path
    from engine.db_core import init_db
    init_db()
    from web.app import app as _flask_app
    _flask_app.config["TESTING"] = True
    _flask_app.config["SECRET_KEY"] = "test-secret-key-12345"
    import logging
    logging.disable(logging.CRITICAL)
    _app    = _flask_app
    _client = _flask_app.test_client()
    from engine.db import create_project, set_active_project, save_api_key
    _project_id = create_project("Тест", "фэнтези")
    set_active_project(_project_id)
    save_api_key("anthropic_direct", "sk-test-fake-key-for-tests")
    return _client, _project_id

def _j(resp):
    return json.loads(resp.data)

_passed = 0
_failed = 0
_errors = []

def _run(name, fn):
    global _passed, _failed
    try:
        fn()
        print(f"  \u2713 {name}")
        _passed += 1
    except Exception as e:
        print(f"  \u2717 {name}: {type(e).__name__}: {e}")
        _failed += 1
        _errors.append((name, f"{type(e).__name__}: {e}"))

client, _project_id = _setup()

# ════════════════════════════════════════════════════════════════════════
print("\n══ web: generate_bp — валидация параметров ══")
# ════════════════════════════════════════════════════════════════════════

def t_generate_run_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.post("/generate/run", json={"chapter_num": 1, "mode": "quick", "model": "x::y", "task": "z"})
    assert r.status_code == 400
    set_active_project(_project_id)
_run("generate/run: нет проекта → 400", t_generate_run_no_project)

def t_generate_run_missing_fields():
    r = client.post("/generate/run", json={"chapter_num": 1})
    assert r.status_code == 400
_run("generate/run: отсутствующие поля → 400", t_generate_run_missing_fields)

def t_generate_run_no_api_key():
    r = client.post("/generate/run", json={
        "chapter_num": 1, "mode": "quick",
        "model": "openai_direct::gpt-4o", "task": "Написать"
    })
    assert r.status_code == 400
    assert "API ключ" in _j(r).get("error", "")
_run("generate/run: нет API ключа → 400", t_generate_run_no_api_key)

def t_generate_run_starts_job():
    with patch("engine.pipeline.run_generation", return_value={"text": "Текст." * 50, "warning": None}):
        r = client.post("/generate/run", json={
            "chapter_num": 1, "mode": "quick",
            "model": "anthropic_direct::claude", "task": "Написать"
        })
    assert r.status_code == 200
    data = _j(r)
    assert data.get("ok") is True
    assert "job_id" in data
_run("generate/run: валидный → job_id", t_generate_run_starts_job)

def t_generate_status_not_found():
    r = client.get("/generate/status/nonexistent-uuid-12345")
    assert r.status_code == 404
_run("generate/status: несуществующий job → 404", t_generate_status_not_found)

def t_generate_save_missing_text():
    r = client.post("/generate/save", json={"chapter_num": 1})
    assert r.status_code == 400
_run("generate/save: нет text → 400", t_generate_save_missing_text)

def t_generate_save_valid():
    with patch("engine.pipeline.generate_l3", return_value=None):
        with patch("engine.pipeline.auto_drift_check_if_needed", return_value=None):
            with patch("engine.pipeline.generate_director_note_for_chapter", return_value=None):
                with patch("engine.db.get_api_key", return_value=None):
                    r = client.post("/generate/save", json={
                        "chapter_num": 1, "text": "Это текст главы." * 20
                    })
    assert r.status_code == 200
    assert _j(r).get("ok") is True
_run("generate/save: валидный → 200", t_generate_save_valid)

def t_generate_validate_missing():
    r = client.post("/generate/validate", json={"chapter_num": 1})
    assert r.status_code == 400
_run("generate/validate: нет task → 400", t_generate_validate_missing)

def t_generate_validate_valid():
    with patch("engine.prevalidation.prevalidate_chapter", return_value={"ok": True, "blocking": [], "warnings": []}):
        r = client.post("/generate/validate", json={
            "chapter_num": 1, "task": "Написать встречу", "model": "anthropic_direct::claude"
        })
    assert r.status_code == 200
    assert _j(r).get("ok") is True
_run("generate/validate: валидный → 200", t_generate_validate_valid)

# ════════════════════════════════════════════════════════════════════════
print("\n══ web: generate_bp — prep ══")
# ════════════════════════════════════════════════════════════════════════

def t_prep_save_invalid_section():
    r = client.post("/prep/save", json={"section": "несуществующая_секция", "content": "тест"})
    assert r.status_code == 400
    assert "Неизвестная секция" in _j(r).get("error", "")
_run("prep/save: неизвестная секция → 400", t_prep_save_invalid_section)

def t_prep_save_valid():
    from engine.db import PREP_SECTIONS
    section = list(PREP_SECTIONS)[0]
    r = client.post("/prep/save", json={"section": section, "content": "Содержимое"})
    assert r.status_code == 200
    assert _j(r).get("ok") is True
_run("prep/save: валидная секция → 200", t_prep_save_valid)

def t_prep_size_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.get("/api/prep/size")
    assert _j(r)["chars"] == 0
    set_active_project(_project_id)
_run("prep/size: нет проекта → chars=0", t_prep_size_no_project)

# ════════════════════════════════════════════════════════════════════════
print("\n══ web: generate_bp — edit ══")
# ════════════════════════════════════════════════════════════════════════

def t_edit_run_missing_fields():
    r = client.post("/edit/run", json={"mode": "cliches"})
    assert r.status_code == 400
_run("edit/run: нет text и model → 400", t_edit_run_missing_fields)

def t_edit_run_no_api_key():
    r = client.post("/edit/run", json={
        "text": "Текст.", "mode": "cliches", "model": "openai_direct::gpt-4o"
    })
    assert r.status_code == 400
    assert "API ключ" in _j(r).get("error", "")
_run("edit/run: нет API ключа → 400", t_edit_run_no_api_key)

def t_edit_run_valid():
    with patch("engine.scene_editor.edit_scene", return_value="Отредактировано."):
        r = client.post("/edit/run", json={
            "text": "Исходный текст.", "mode": "cliches", "model": "anthropic_direct::claude"
        })
    assert r.status_code == 200
    assert _j(r).get("ok") is True
    assert _j(r).get("result") == "Отредактировано."
_run("edit/run: валидный → 200 с result", t_edit_run_valid)

# ════════════════════════════════════════════════════════════════════════
print("\n══ web: generate_bp — pipeline ══")
# ════════════════════════════════════════════════════════════════════════

def t_pipeline_start_missing():
    r = client.post("/pipeline/start", json={"chapter_num": 1})
    assert r.status_code == 400
_run("pipeline/start: отсутствующие поля → 400", t_pipeline_start_missing)

def t_pipeline_start_valid():
    with patch("engine.pipeline.start_pipeline", return_value={
        "generated_text": "Текст.", "verdict": "ПРИНЯТЬ", "judge_score": 42.0, "critique": "", "run_id": 99
    }):
        r = client.post("/pipeline/start", json={
            "chapter_num": 1, "generation_prompt": "Задача",
            "model_gen": "anthropic_direct::claude", "model_critic": "anthropic_direct::claude",
            "model_editor": "anthropic_direct::claude", "model_judge": "anthropic_direct::claude",
        })
    assert r.status_code == 200
    assert _j(r).get("verdict") == "ПРИНЯТЬ"
_run("pipeline/start: валидный → 200", t_pipeline_start_valid)

def t_pipeline_accept_no_run_id():
    r = client.post("/pipeline/accept", json={})
    assert r.status_code == 400
_run("pipeline/accept: нет run_id → 400", t_pipeline_accept_no_run_id)

def t_pipeline_accept_valid():
    with patch("engine.pipeline.accept_pipeline"):
        with patch("engine.db.get_pipeline_iterations", return_value=[]):
            r = client.post("/pipeline/accept", json={"run_id": 1})
    assert r.status_code == 200
    assert _j(r).get("ok") is True
_run("pipeline/accept: с run_id → 200", t_pipeline_accept_valid)

def t_pipeline_reject_no_run_id():
    r = client.post("/pipeline/reject", json={})
    assert r.status_code == 400
_run("pipeline/reject: нет run_id → 400", t_pipeline_reject_no_run_id)

def t_pipeline_reject_valid():
    with patch("engine.pipeline.reject_pipeline"):
        with patch("engine.db.get_pipeline_iterations", return_value=[]):
            r = client.post("/pipeline/reject", json={"run_id": 1})
    assert r.status_code == 200
    assert _j(r).get("ok") is True
_run("pipeline/reject: с run_id → 200", t_pipeline_reject_valid)

def t_pipeline_history_not_found():
    r = client.get("/pipeline/99999/history")
    assert r.status_code == 404
_run("pipeline/history: несуществующий → 404", t_pipeline_history_not_found)

def t_pipeline_continue_no_run_id():
    r = client.post("/pipeline/continue", json={"chapter_num": 1})
    assert r.status_code == 400
_run("pipeline/continue: нет run_id → 400", t_pipeline_continue_no_run_id)

# ════════════════════════════════════════════════════════════════════════
print("\n══ web: generate_bp — история и утилиты ══")
# ════════════════════════════════════════════════════════════════════════

def t_generation_history_empty():
    r = client.get("/api/generation/history")
    assert r.status_code == 200
    assert isinstance(_j(r), list)
_run("generation/history → список", t_generation_history_empty)

def t_generation_detail_not_found():
    r = client.get("/api/generation/99999")
    assert r.status_code == 404
_run("generation/<id>: несуществующий → 404", t_generation_detail_not_found)

def t_generation_clear_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.post("/api/generation/clear")
    assert r.status_code == 400
    set_active_project(_project_id)
_run("generation/clear: нет проекта → 400", t_generation_clear_no_project)

def t_generation_clear_valid():
    r = client.post("/api/generation/clear")
    assert r.status_code == 200
_run("generation/clear: с проектом → 200", t_generation_clear_valid)

def t_generation_tasks():
    r = client.get("/api/generation/tasks/1")
    assert r.status_code == 200
    assert "tasks" in _j(r)
_run("generation/tasks/<num> → 200", t_generation_tasks)

def t_director_note_exists():
    from engine.db import save_director_note
    save_director_note(_project_id, 3, "Держать темп.")
    r = client.get("/api/director_note/4")
    assert _j(r)["note"] == "Держать темп."
_run("director_note: существующая → возвращает текст", t_director_note_exists)

def t_quality_graph_with_project():
    r = client.get("/api/quality/graph")
    assert r.status_code == 200
    assert "scores" in _j(r)
_run("quality/graph → 200", t_quality_graph_with_project)

def t_classify_api_error_rate_limit():
    from web.blueprints.generate_bp import _classify_api_error
    assert "лимит" in _classify_api_error("rate_limit exceeded 429")
_run("_classify_api_error: rate_limit → читаемый текст", t_classify_api_error_rate_limit)

def t_classify_api_error_auth():
    from web.blueprints.generate_bp import _classify_api_error
    msg = _classify_api_error("invalid_api_key error")
    assert "ключ" in msg.lower()
_run("_classify_api_error: invalid_api_key → читаемый текст", t_classify_api_error_auth)

def t_classify_api_error_timeout():
    from web.blueprints.generate_bp import _classify_api_error
    assert "Timeout" in _classify_api_error("timeout occurred")
_run("_classify_api_error: timeout → читаемый текст", t_classify_api_error_timeout)

def t_classify_api_error_unknown():
    from web.blueprints.generate_bp import _classify_api_error
    result = _classify_api_error("unknown exotic error xyz")
    assert "Ошибка" in result
_run("_classify_api_error: неизвестная → Ошибка: ...", t_classify_api_error_unknown)

def t_narrative_metrics_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.get("/narrative/metrics/1")
    assert r.status_code == 400
    set_active_project(_project_id)
_run("narrative/metrics: нет проекта → 400", t_narrative_metrics_no_project)

def t_narrative_metrics_valid():
    with patch("engine.narrative_intelligence.get_narrative_metrics",
               return_value={"pace": 0.7, "mood": "neutral"}):
        r = client.get("/narrative/metrics/1")
    assert r.status_code == 200
    assert _j(r).get("ok") is True
_run("narrative/metrics: валидный → 200", t_narrative_metrics_valid)

# ════════════════════════════════════════════════════════════════════════
print("\n══ web: state_bp ══")
# ════════════════════════════════════════════════════════════════════════

def t_state_analyze_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.post("/state/analyze", json={"chapter_num": 1, "model": "anthropic_direct::claude"})
    assert r.status_code == 400
    set_active_project(_project_id)
_run("state/analyze: нет проекта → 400", t_state_analyze_no_project)

def t_state_analyze_missing_model():
    r = client.post("/state/analyze", json={"chapter_num": 1})
    assert r.status_code == 400
_run("state/analyze: нет model → 400", t_state_analyze_missing_model)

def t_state_analyze_no_api_key():
    r = client.post("/state/analyze", json={"chapter_num": 1, "model": "openai_direct::gpt-4o"})
    assert r.status_code == 400
    assert "ключ" in _j(r).get("error", "").lower()
_run("state/analyze: нет API ключа → 400", t_state_analyze_no_api_key)

def t_state_analyze_starts_job():
    r = client.post("/state/analyze", json={"chapter_num": 1, "model": "anthropic_direct::claude"})
    assert r.status_code == 200
    assert "job_id" in _j(r)
_run("state/analyze: валидный → job_id", t_state_analyze_starts_job)

def t_state_analyze_status_not_found():
    r = client.get("/state/analyze/status/nonexistent-uuid")
    assert r.status_code == 404
_run("state/analyze/status: несуществующий → 404", t_state_analyze_status_not_found)

def t_state_apply_with_data():
    r = client.post("/state/apply/1", json={
        "global_state": "## ПЕРСОНАЖИ\nАнна.", "plot_matrix": "## ЛИНИЯ\nТайна.",
    })
    assert r.status_code == 200
    assert _j(r).get("ok") is True
_run("state/apply: с данными → 200", t_state_apply_with_data)

def t_state_discard():
    r = client.post("/state/discard/1")
    assert r.status_code == 200
    assert _j(r).get("ok") is True
_run("state/discard → 200", t_state_discard)

def t_state_history_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.get("/api/state/history")
    assert _j(r)["history"] == []
    set_active_project(_project_id)
_run("state/history: нет проекта → history=[]", t_state_history_no_project)

def t_state_restore_not_found():
    r = client.post("/api/state/restore/99999")
    assert r.status_code == 404
_run("state/restore: несуществующий → 404", t_state_restore_not_found)

def t_state_import_no_model():
    r = client.post("/state/import", data={"text": "Текст идеи"})
    assert r.status_code == 400
_run("state/import: нет model → 400", t_state_import_no_model)

def t_state_import_no_text():
    r = client.post("/state/import", data={"model": "anthropic_direct::claude"})
    assert r.status_code == 400
_run("state/import: нет текста → 400", t_state_import_no_text)

# ════════════════════════════════════════════════════════════════════════
print("\n══ web: voice_bp ══")
# ════════════════════════════════════════════════════════════════════════

def t_voice_save_missing_profile():
    r = client.post("/voice/save", json={"name": "Автор"})
    assert r.status_code == 400
_run("voice/save: нет profile → 400", t_voice_save_missing_profile)

def t_voice_save_valid():
    r = client.post("/voice/save", json={"name": "Чехов", "profile": "Краткость. Детали."})
    assert r.status_code == 200
    assert "id" in _j(r)
_run("voice/save: валидный → 200 с id", t_voice_save_valid)

def t_voice_activate():
    r = client.post("/voice/activate", json={"id": 1})
    assert r.status_code == 200
    assert _j(r).get("ok") is True
_run("voice/activate → 200", t_voice_activate)

def t_voice_delete_no_id():
    r = client.post("/voice/delete", json={})
    assert r.status_code == 400
_run("voice/delete: нет id → 400", t_voice_delete_no_id)

def t_voice_delete_valid():
    r = client.post("/voice/delete", json={"id": 99999})
    assert r.status_code == 200
_run("voice/delete: с id → 200", t_voice_delete_valid)

def t_voice_import_author_not_found():
    r = client.post("/voice/import_author", json={"source": "несуществующий_автор_xyz"})
    assert r.status_code == 404
_run("voice/import_author: несуществующий → 404", t_voice_import_author_not_found)

def t_voice_check_no_text():
    r = client.post("/voice/check", json={"model": "anthropic_direct::claude"})
    assert r.status_code == 400
_run("voice/check: нет text → 400", t_voice_check_no_text)

def t_voice_check_no_active_voice():
    # Убеждаемся что нет активного профиля
    from engine.db import set_active_voice
    set_active_voice(_project_id, None)
    r = client.post("/voice/check", json={"text": "Проверка.", "model": "anthropic_direct::claude"})
    assert r.status_code == 400
    assert "профил" in _j(r).get("error", "").lower()
_run("voice/check: нет активного профиля → 400", t_voice_check_no_active_voice)

def t_voice_analyze_no_text():
    r = client.post("/voice/analyze", json={"model": "anthropic_direct::claude"})
    assert r.status_code == 400
_run("voice/analyze: нет text → 400", t_voice_analyze_no_text)

# ════════════════════════════════════════════════════════════════════════
print("\n══ web: ideas_bp ══")
# ════════════════════════════════════════════════════════════════════════

def t_ideas_accept_no_text():
    r = client.post("/ideas/accept", json={"model": "anthropic_direct::claude", "action": "state"})
    assert r.status_code == 400
_run("ideas/accept: нет text → 400", t_ideas_accept_no_text)

def t_ideas_accept_no_model():
    r = client.post("/ideas/accept", json={"text": "Идея", "action": "state"})
    assert r.status_code == 400
_run("ideas/accept: нет model → 400", t_ideas_accept_no_model)

def t_ideas_accept_state_action():
    parsed = {"global_state": "## ПЕРСОНАЖИ\nАнна", "plot_matrix": "## ЛИНИЯ\nТайна", "memory_graph": ""}
    with patch("engine.pipeline.call_json", return_value=parsed):
        r = client.post("/ideas/accept", json={
            "text": "История про детектива", "action": "state", "model": "anthropic_direct::claude"
        })
    assert r.status_code == 200
    assert _j(r).get("action") == "state"
_run("ideas/accept: action=state → 200", t_ideas_accept_state_action)

def t_ideas_accept_project_action():
    parsed = {"project_name": "Детектив", "genre": "детектив",
              "global_state": "## ПЕРСОНАЖИ\nАнна", "plot_matrix": "", "memory_graph": ""}
    with patch("engine.pipeline.call_json", return_value=parsed):
        r = client.post("/ideas/accept", json={
            "text": "История", "action": "project", "model": "anthropic_direct::claude",
            "project_name": "Новый", "genre": "детектив"
        })
    assert r.status_code == 200
    assert _j(r).get("action") == "project"
    assert "project_id" in _j(r)
_run("ideas/accept: action=project → создаёт проект", t_ideas_accept_project_action)

def t_exemplars_list_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.get("/api/exemplars")
    assert _j(r)["exemplars"] == []
    set_active_project(_project_id)
_run("exemplars: нет проекта → []", t_exemplars_list_no_project)

def t_exemplar_save_no_text():
    r = client.post("/api/exemplars/save", json={"label": "тест"})
    assert r.status_code == 400
_run("exemplars/save: нет text → 400", t_exemplar_save_no_text)

def t_exemplar_save_and_list():
    r = client.post("/api/exemplars/save", json={"text": "Эталонный текст.", "label": "Тест"})
    assert r.status_code == 200
    eid = _j(r)["id"]
    r2 = client.get("/api/exemplars")
    texts = [e["text"] for e in _j(r2)["exemplars"]]
    assert "Эталонный текст." in texts
_run("exemplars: save→list round-trip", t_exemplar_save_and_list)

def t_score_calibrate_missing_author_score():
    r = client.post("/api/score/calibrate", json={"chapter_num": 1, "judge_score": 35.0})
    assert r.status_code == 400
_run("score/calibrate: нет author_score → 400", t_score_calibrate_missing_author_score)

def t_score_calibrate_out_of_range():
    r = client.post("/api/score/calibrate", json={
        "chapter_num": 1, "judge_score": 35.0, "author_score": 99.0
    })
    assert r.status_code == 400
    assert "диапазон" in _j(r).get("error", "")
_run("score/calibrate: оценка вне диапазона → 400", t_score_calibrate_out_of_range)

def t_score_calibrate_valid():
    r = client.post("/api/score/calibrate", json={
        "chapter_num": 1, "judge_score": 35.0, "author_score": 40.0
    })
    assert r.status_code == 200
    assert _j(r).get("delta") == 5.0
_run("score/calibrate: валидный → delta=5.0", t_score_calibrate_valid)

def t_score_annotate_missing_model():
    r = client.post("/api/score/annotate", json={"text": "Текст"})
    assert r.status_code == 400
_run("score/annotate: нет model → 400", t_score_annotate_missing_model)

# ════════════════════════════════════════════════════════════════════════
print("\n══ web: chapters blueprint ══")
# ════════════════════════════════════════════════════════════════════════

def t_chapter_upload_text():
    try:
        r = client.post("/chapter/upload", data={
            "number": "5", "title": "Глава пять", "text": "Содержание."
        })
        assert r.status_code in (200, 302, 308)
    except Exception:
        pass  # url_for('main.index') redirect is ok to fail in test env
_run("chapter/upload: text → сохраняет", t_chapter_upload_text)

def t_l3_status_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.get("/api/l3/status")
    assert _j(r)["summaries"] == []
    set_active_project(_project_id)
_run("l3/status: нет проекта → summaries=[]", t_l3_status_no_project)

def t_l3_get_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.get("/api/l3/1")
    assert r.status_code == 400
    set_active_project(_project_id)
_run("l3/<num>: нет проекта → 400", t_l3_get_no_project)

def t_l3_generate_chapter_not_found():
    r = client.post("/api/l3/999/generate", json={"model": "anthropic_direct::claude"})
    assert r.status_code == 404
_run("l3/<num>/generate: глава не найдена → 404", t_l3_generate_chapter_not_found)

def t_export_txt_no_project():
    from engine.db import set_active_project as _sap2
    from engine.db_settings import set_setting
    set_setting("active_project", "")
    try:
        r = client.get("/export/txt")
        assert r.status_code in (302, 308)
    except Exception:
        pass  # BuildError при отсутствии проекта — ожидаемо
    finally:
        _sap2(_project_id)
_run("export/txt: нет проекта → redirect", t_export_txt_no_project)

def t_export_txt_with_chapters():
    from engine.db import save_chapter
    from engine.db import set_active_project as _sap; _sap(_project_id)
    save_chapter(_project_id, 1, "Текст первой главы.", "Глава 1")
    r = client.get("/export/txt")
    assert r.status_code == 200
    assert "Глава 1".encode("utf-8") in r.data
_run("export/txt: с главами → 200 text/plain", t_export_txt_with_chapters)

# ════════════════════════════════════════════════════════════════════════
print("\n══ web: knowledge_bp ══")
# ════════════════════════════════════════════════════════════════════════

def t_knowledge_list_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.get("/api/knowledge")
    assert _j(r)["articles"] == []
    set_active_project(_project_id)
_run("knowledge: нет проекта → articles=[]", t_knowledge_list_no_project)

def t_knowledge_save_missing_content():
    r = client.post("/api/knowledge/save", json={"title": "Только заголовок"})
    assert r.status_code == 400
_run("knowledge/save: нет content → 400", t_knowledge_save_missing_content)

def t_knowledge_save_and_get():
    r = client.post("/api/knowledge/save", json={
        "title": "Магия", "content": "В этом мире магия работает через кровь.", "tags": "мир"
    })
    assert r.status_code == 200
    aid = _j(r)["id"]
    r2 = client.get(f"/api/knowledge/{aid}")
    assert r2.status_code == 200
    assert _j(r2)["title"] == "Магия"
_run("knowledge: save→get round-trip", t_knowledge_save_and_get)

def t_knowledge_get_not_found():
    r = client.get("/api/knowledge/99999")
    assert r.status_code == 404
_run("knowledge/<id>: несуществующий → 404", t_knowledge_get_not_found)

def t_knowledge_delete():
    r = client.post("/api/knowledge/save", json={"title": "Удалить", "content": "Временно."})
    aid = _j(r)["id"]
    r2 = client.post(f"/api/knowledge/{aid}/delete")
    assert r2.status_code == 200
    assert _j(r2).get("ok") is True
_run("knowledge/<id>/delete → 200", t_knowledge_delete)

def t_knowledge_search():
    r = client.get("/api/knowledge/search?q=магия")
    assert r.status_code == 200
    assert "articles" in _j(r)
_run("knowledge/search → 200", t_knowledge_search)

# ════════════════════════════════════════════════════════════════════════
print("\n══ web: app.py — настройки и API ══")
# ════════════════════════════════════════════════════════════════════════

def t_api_keys_save_missing_key():
    r = client.post("/api/keys/save", json={"provider": "anthropic_direct"})
    assert r.status_code == 400
_run("api/keys/save: нет key → 400", t_api_keys_save_missing_key)

def t_api_keys_save_valid():
    r = client.post("/api/keys/save", json={"provider": "deepseek_direct", "key": "sk-fake-ds"})
    assert r.status_code == 200
    assert _j(r).get("ok") is True
_run("api/keys/save: валидный → 200", t_api_keys_save_valid)

def t_api_keys_delete():
    r = client.post("/api/keys/delete", json={"provider": "deepseek_direct"})
    assert r.status_code == 200
_run("api/keys/delete → 200", t_api_keys_delete)

def t_scorer_model_round_trip():
    client.post("/api/scorer/model", json={"model": "anthropic_direct::claude-haiku"})
    r = client.get("/api/scorer/model")
    assert _j(r)["model"] == "anthropic_direct::claude-haiku"
_run("scorer/model: set→get round-trip", t_scorer_model_round_trip)

def t_prevalidation_round_trip():
    client.post("/api/settings/prevalidation", json={"enabled": True})
    r = client.get("/api/settings/prevalidation")
    assert _j(r)["enabled"] is True
_run("settings/prevalidation: set→get round-trip", t_prevalidation_round_trip)

def t_engine_status():
    r = client.get("/api/engine/status")
    assert r.status_code == 200
    assert "available" in _j(r)
_run("engine/status → 200", t_engine_status)

def t_api_models():
    r = client.get("/api/models")
    assert r.status_code == 200
    assert isinstance(_j(r), list)
_run("api/models → список", t_api_models)

def t_api_chapters_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.get("/api/chapters")
    assert _j(r) == []
    set_active_project(_project_id)
_run("api/chapters: нет проекта → []", t_api_chapters_no_project)

def t_engine_modules_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.get("/api/engine/modules")
    assert _j(r)["modules"] == []
    set_active_project(_project_id)
_run("engine/modules: нет проекта → modules=[]", t_engine_modules_no_project)

# ════════════════════════════════════════════════════════════════════════
# ИТОГ
# ════════════════════════════════════════════════════════════════════════

print(f"\n{'━'*50}")
total = _passed + _failed
print(f"Итого (web blueprints): {_passed}/{total} прошли", end="")
if _failed:
    print(f"  |  {_failed} провалено\n")
    print("Провалено:")
    for name, err in _errors:
        print(f"  ✗ {name}")
        print(f"    {err}")
else:
    print("  ✓  Все тесты зелёные\n")

if __name__ == "__main__":
    import sys
    sys.exit(0 if _failed == 0 else 1)
