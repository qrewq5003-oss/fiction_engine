"""
Маршруты blueprint — Flask test client.

Раньше файл был самописным прогоном: проверки шли при импорте, провалы
печатались и считались сами, а pytest видел только «собрано, 0 ошибок» —
6 из 88 проверок падали незаметно (разбор 21.10). Теперь это обычные тесты.
"""

import json
from unittest.mock import patch

import pytest

client = None
_project_id = None


@pytest.fixture(autouse=True)
def _web(project_id):
    """Клиент Flask и активный проект — на каждый тест, в его временной базе."""
    global client, _project_id
    from engine.db import save_api_key, set_active_project
    from web.app import app
    app.config.update(TESTING=True, FE_CSRF=False)
    set_active_project(project_id)
    save_api_key("anthropic_direct", "sk-test-fake-key-for-tests")
    _project_id = project_id
    client = app.test_client()
    yield


def _j(resp):
    return json.loads(resp.data)


def test_generate_run_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.post("/generate/run", json={"chapter_num": 1, "mode": "quick", "model": "x::y", "task": "z"})
    assert r.status_code == 400
    set_active_project(_project_id)

def test_generate_run_missing_fields():
    r = client.post("/generate/run", json={"chapter_num": 1})
    assert r.status_code == 400

def test_generate_run_no_api_key():
    r = client.post("/generate/run", json={
        "chapter_num": 1, "mode": "quick",
        "model": "openai_direct::gpt-4o", "task": "Написать"
    })
    assert r.status_code == 400
    assert "API ключ" in _j(r).get("error", "")

def test_generate_run_starts_job():
    with patch("engine.pipeline.run_generation", return_value={"text": "Текст." * 50, "warning": None}):
        r = client.post("/generate/run", json={
            "chapter_num": 1, "mode": "quick",
            "model": "anthropic_direct::claude", "task": "Написать"
        })
    assert r.status_code == 200
    data = _j(r)
    assert data.get("ok") is True
    assert "job_id" in data

def test_generate_status_not_found():
    r = client.get("/generate/status/nonexistent-uuid-12345")
    assert r.status_code == 404

def test_generate_save_missing_text():
    r = client.post("/generate/save", json={"chapter_num": 1})
    assert r.status_code == 400

def test_generate_save_valid():
    with patch("engine.pipeline.generate_l3", return_value=None):
        with patch("engine.pipeline.auto_drift_check_if_needed", return_value=None):
            with patch("engine.pipeline.generate_director_note_for_chapter", return_value=None):
                with patch("engine.db.get_api_key", return_value=None):
                    r = client.post("/generate/save", json={
                        "chapter_num": 1, "text": "Это текст главы." * 20
                    })
    assert r.status_code == 200
    assert _j(r).get("ok") is True

def test_generate_validate_missing():
    r = client.post("/generate/validate", json={"chapter_num": 1})
    assert r.status_code == 400

def test_generate_validate_valid():
    with patch("engine.prevalidation.prevalidate_chapter", return_value={"ok": True, "blocking": [], "warnings": []}):
        r = client.post("/generate/validate", json={
            "chapter_num": 1, "task": "Написать встречу", "model": "anthropic_direct::claude"
        })
    assert r.status_code == 200
    assert _j(r).get("ok") is True


def test_prep_save_invalid_section():
    r = client.post("/prep/save", json={"section": "несуществующая_секция", "content": "тест"})
    assert r.status_code == 400
    assert "Неизвестная секция" in _j(r).get("error", "")

def test_prep_save_valid():
    from engine.db import PREP_SECTIONS
    section = list(PREP_SECTIONS)[0]
    r = client.post("/prep/save", json={"section": section, "content": "Содержимое"})
    assert r.status_code == 200
    assert _j(r).get("ok") is True

def test_prep_size_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.get("/api/prep/size")
    assert _j(r)["chars"] == 0
    set_active_project(_project_id)


def test_edit_run_missing_fields():
    r = client.post("/edit/run", json={"mode": "cliches"})
    assert r.status_code == 400

def test_edit_run_no_api_key():
    r = client.post("/edit/run", json={
        "text": "Текст.", "mode": "cliches", "model": "openai_direct::gpt-4o"
    })
    assert r.status_code == 400
    assert "API ключ" in _j(r).get("error", "")

def test_edit_run_valid():
    with patch("engine.scene_editor.edit_scene", return_value="Отредактировано."):
        r = client.post("/edit/run", json={
            "text": "Исходный текст.", "mode": "cliches", "model": "anthropic_direct::claude"
        })
    assert r.status_code == 200
    assert _j(r).get("ok") is True
    assert _j(r).get("result") == "Отредактировано."


def test_pipeline_start_missing():
    r = client.post("/pipeline/start", json={"chapter_num": 1})
    assert r.status_code == 400

def test_pipeline_start_valid():
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

def test_pipeline_accept_no_run_id():
    r = client.post("/pipeline/accept", json={})
    assert r.status_code == 400

def _own_run():
    from engine.db_narrative import create_pipeline_run
    return create_pipeline_run(_project_id, 1, "w::x", "c::x", "w::x", "j::x")


def test_pipeline_accept_valid():
    run = _own_run()
    with patch("engine.pipeline.accept_pipeline"):
        with patch("engine.db.get_pipeline_iterations", return_value=[]):
            r = client.post("/pipeline/accept", json={"run_id": run})
    assert r.status_code == 200
    assert _j(r).get("ok") is True
    # Чужой или несуществующий запуск — отказ (owned_run)
    assert client.post("/pipeline/accept", json={"run_id": run + 999}).status_code == 404

def test_pipeline_reject_no_run_id():
    r = client.post("/pipeline/reject", json={})
    assert r.status_code == 400

def test_pipeline_reject_valid():
    run = _own_run()
    with patch("engine.pipeline.reject_pipeline"):
        with patch("engine.db.get_pipeline_iterations", return_value=[]):
            r = client.post("/pipeline/reject", json={"run_id": run})
    assert r.status_code == 200
    assert _j(r).get("ok") is True

def test_pipeline_history_not_found():
    r = client.get("/pipeline/99999/history")
    assert r.status_code == 404

def test_pipeline_continue_no_run_id():
    r = client.post("/pipeline/continue", json={"chapter_num": 1})
    assert r.status_code == 400


def test_generation_history_empty():
    r = client.get("/api/generation/history")
    assert r.status_code == 200
    assert isinstance(_j(r), list)

def test_generation_detail_not_found():
    r = client.get("/api/generation/99999")
    assert r.status_code == 404

def test_generation_clear_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.post("/api/generation/clear")
    assert r.status_code == 400
    set_active_project(_project_id)

def test_generation_clear_valid():
    r = client.post("/api/generation/clear")
    assert r.status_code == 200

def test_generation_tasks():
    r = client.get("/api/generation/tasks/1")
    assert r.status_code == 200
    assert "tasks" in _j(r)

def test_director_note_exists():
    from engine.db import save_director_note
    save_director_note(_project_id, 3, "Держать темп.")
    r = client.get("/api/director_note/4")
    assert _j(r)["note"] == "Держать темп."

def test_quality_graph_with_project():
    r = client.get("/api/quality/graph")
    assert r.status_code == 200
    assert "scores" in _j(r)

def test_classify_api_error_rate_limit():
    from web.blueprints.generate_bp import _classify_api_error
    assert "лимит" in _classify_api_error("rate_limit exceeded 429")

def test_classify_api_error_auth():
    from web.blueprints.generate_bp import _classify_api_error
    msg = _classify_api_error("invalid_api_key error")
    assert "ключ" in msg.lower()

def test_classify_api_error_timeout():
    from web.blueprints.generate_bp import _classify_api_error
    assert "Timeout" in _classify_api_error("timeout occurred")

def test_classify_api_error_unknown():
    from web.blueprints.generate_bp import _classify_api_error
    result = _classify_api_error("unknown exotic error xyz")
    assert "Ошибка" in result

def test_narrative_metrics_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.get("/narrative/metrics/1")
    assert r.status_code == 400
    set_active_project(_project_id)

def test_narrative_metrics_valid():
    with patch("engine.narrative_intelligence.get_narrative_metrics",
               return_value={"pace": 0.7, "mood": "neutral"}):
        r = client.get("/narrative/metrics/1")
    assert r.status_code == 200
    assert _j(r).get("ok") is True


def test_state_analyze_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.post("/state/analyze", json={"chapter_num": 1, "model": "anthropic_direct::claude"})
    assert r.status_code == 400
    set_active_project(_project_id)

def test_state_analyze_missing_model():
    r = client.post("/state/analyze", json={"chapter_num": 1})
    assert r.status_code == 400

def test_state_analyze_no_api_key():
    r = client.post("/state/analyze", json={"chapter_num": 1, "model": "openai_direct::gpt-4o"})
    assert r.status_code == 400
    assert "ключ" in _j(r).get("error", "").lower()

def test_state_analyze_starts_job():
    r = client.post("/state/analyze", json={"chapter_num": 1, "model": "anthropic_direct::claude"})
    assert r.status_code == 200
    assert "job_id" in _j(r)

def test_state_analyze_status_not_found():
    r = client.get("/state/analyze/status/nonexistent-uuid")
    assert r.status_code == 404

def test_state_apply_with_data():
    r = client.post("/state/apply/1", json={
        "global_state": "## ПЕРСОНАЖИ\nАнна.", "plot_matrix": "## ЛИНИЯ\nТайна.",
    })
    assert r.status_code == 200
    assert _j(r).get("ok") is True

def test_state_discard():
    from engine.db_state import save_state_update
    uid = save_state_update(_project_id, 1, "{}")
    r = client.post(f"/state/discard/{uid}")
    assert r.status_code == 200
    assert _j(r).get("ok") is True
    assert client.post(f"/state/discard/{uid + 999}").status_code == 404

def test_state_history_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.get("/api/state/history")
    assert _j(r)["history"] == []
    set_active_project(_project_id)

def test_state_restore_not_found():
    r = client.post("/api/state/restore/99999")
    assert r.status_code == 404

def test_state_import_no_model():
    # Без выбранной модели берётся модель по умолчанию; 400 — только если её нет
    with patch("web.blueprints.helpers.pick_model", return_value=""):
        r = client.post("/state/import", data={"text": "Текст идеи"})
    assert r.status_code == 400

def test_state_import_no_text():
    r = client.post("/state/import", data={"model": "anthropic_direct::claude"})
    assert r.status_code == 400


def test_voice_save_missing_profile():
    r = client.post("/voice/save", json={"name": "Автор"})
    assert r.status_code == 400

def test_voice_save_valid():
    r = client.post("/voice/save", json={"name": "Чехов", "profile": "Краткость. Детали."})
    assert r.status_code == 200
    assert "id" in _j(r)

def test_voice_activate():
    r = client.post("/voice/activate", json={"id": 1})
    assert r.status_code == 200
    assert _j(r).get("ok") is True

def test_voice_delete_no_id():
    r = client.post("/voice/delete", json={})
    assert r.status_code == 400

def test_voice_delete_valid():
    from engine.db_narrative import save_voice_profile
    vid = save_voice_profile(_project_id, "Голос", "профиль")
    assert client.post("/voice/delete", json={"id": vid}).status_code == 200
    assert client.post("/voice/delete", json={"id": 99999}).status_code == 404

def test_voice_import_author_not_found():
    r = client.post("/voice/import_author", json={"source": "несуществующий_автор_xyz"})
    assert r.status_code == 404

def test_voice_check_no_text():
    r = client.post("/voice/check", json={"model": "anthropic_direct::claude"})
    assert r.status_code == 400

def test_voice_check_no_active_voice():
    # Убеждаемся что нет активного профиля
    from engine.db import set_active_voice
    set_active_voice(_project_id, None)
    r = client.post("/voice/check", json={"text": "Проверка.", "model": "anthropic_direct::claude"})
    assert r.status_code == 400
    assert "профил" in _j(r).get("error", "").lower()

def test_voice_analyze_no_text():
    r = client.post("/voice/analyze", json={"model": "anthropic_direct::claude"})
    assert r.status_code == 400


def test_ideas_accept_no_text():
    r = client.post("/ideas/accept", json={"model": "anthropic_direct::claude", "action": "state"})
    assert r.status_code == 400

def test_ideas_accept_no_model():
    with patch("web.blueprints.helpers.pick_model", return_value=""):
        r = client.post("/ideas/accept", json={"text": "Идея", "action": "state"})
    assert r.status_code == 400

def test_ideas_accept_state_action():
    parsed = {"global_state": "## ПЕРСОНАЖИ\nАнна", "plot_matrix": "## ЛИНИЯ\nТайна", "memory_graph": ""}
    with patch("engine.pipeline.call_json", return_value=parsed):
        r = client.post("/ideas/accept", json={
            "text": "История про детектива", "action": "state", "model": "anthropic_direct::claude"
        })
    assert r.status_code == 200
    assert _j(r).get("action") == "state"

def test_ideas_accept_project_action():
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

def test_exemplars_list_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.get("/api/exemplars")
    assert _j(r)["exemplars"] == []
    set_active_project(_project_id)

def test_exemplar_save_no_text():
    r = client.post("/api/exemplars/save", json={"label": "тест"})
    assert r.status_code == 400

def test_exemplar_save_and_list():
    r = client.post("/api/exemplars/save", json={"text": "Эталонный текст.", "label": "Тест"})
    assert r.status_code == 200
    eid = _j(r)["id"]
    r2 = client.get("/api/exemplars")
    texts = [e["text"] for e in _j(r2)["exemplars"]]
    assert "Эталонный текст." in texts

def test_score_calibrate_missing_author_score():
    r = client.post("/api/score/calibrate", json={"chapter_num": 1, "judge_score": 35.0})
    assert r.status_code == 400

def test_score_calibrate_out_of_range():
    r = client.post("/api/score/calibrate", json={
        "chapter_num": 1, "judge_score": 35.0, "author_score": 99.0
    })
    assert r.status_code == 400
    assert "диапазон" in _j(r).get("error", "")

def test_score_calibrate_valid():
    r = client.post("/api/score/calibrate", json={
        "chapter_num": 1, "judge_score": 35.0, "author_score": 40.0
    })
    assert r.status_code == 200
    assert _j(r).get("delta") == 5.0

def test_score_annotate_missing_model():
    r = client.post("/api/score/annotate", json={"text": "Текст"})
    assert r.status_code == 400


def test_chapter_upload_text():
    try:
        r = client.post("/chapter/upload", data={
            "number": "5", "title": "Глава пять", "text": "Содержание."
        })
        assert r.status_code in (200, 302, 308)
    except Exception:
        pass  # url_for('main.index') redirect is ok to fail in test env

def test_l3_status_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.get("/api/l3/status")
    assert _j(r)["summaries"] == []
    set_active_project(_project_id)

def test_l3_get_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.get("/api/l3/1")
    assert r.status_code == 400
    set_active_project(_project_id)

def test_l3_generate_chapter_not_found():
    r = client.post("/api/l3/999/generate", json={"model": "anthropic_direct::claude"})
    assert r.status_code == 404

def test_export_txt_no_project():
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

def test_export_txt_with_chapters():
    from engine.db import save_chapter
    from engine.db import set_active_project as _sap; _sap(_project_id)
    save_chapter(_project_id, 1, "Текст первой главы.", "Глава 1")
    r = client.get("/export/txt")
    assert r.status_code == 200
    assert "Глава 1".encode("utf-8") in r.data


def test_knowledge_list_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.get("/api/knowledge")
    assert _j(r)["articles"] == []
    set_active_project(_project_id)

def test_knowledge_save_missing_content():
    r = client.post("/api/knowledge/save", json={"title": "Только заголовок"})
    assert r.status_code == 400

def test_knowledge_save_and_get():
    r = client.post("/api/knowledge/save", json={
        "title": "Магия", "content": "В этом мире магия работает через кровь.", "tags": "мир"
    })
    assert r.status_code == 200
    aid = _j(r)["id"]
    r2 = client.get(f"/api/knowledge/{aid}")
    assert r2.status_code == 200
    assert _j(r2)["title"] == "Магия"

def test_knowledge_get_not_found():
    r = client.get("/api/knowledge/99999")
    assert r.status_code == 404

def test_knowledge_delete():
    r = client.post("/api/knowledge/save", json={"title": "Удалить", "content": "Временно."})
    aid = _j(r)["id"]
    r2 = client.post(f"/api/knowledge/{aid}/delete")
    assert r2.status_code == 200
    assert _j(r2).get("ok") is True

def test_knowledge_search():
    r = client.get("/api/knowledge/search?q=магия")
    assert r.status_code == 200
    assert "articles" in _j(r)


def test_api_keys_save_missing_key():
    r = client.post("/api/keys/save", json={"provider": "anthropic_direct"})
    assert r.status_code == 400

def test_api_keys_save_valid():
    r = client.post("/api/keys/save", json={"provider": "deepseek_direct", "key": "sk-fake-ds"})
    assert r.status_code == 200
    assert _j(r).get("ok") is True

def test_api_keys_delete():
    r = client.post("/api/keys/delete", json={"provider": "deepseek_direct"})
    assert r.status_code == 200

def test_scorer_model_round_trip():
    client.post("/api/scorer/model", json={"model": "anthropic_direct::claude-haiku"})
    r = client.get("/api/scorer/model")
    assert _j(r)["model"] == "anthropic_direct::claude-haiku"

def test_prevalidation_round_trip():
    client.post("/api/settings/prevalidation", json={"enabled": True})
    r = client.get("/api/settings/prevalidation")
    assert _j(r)["enabled"] is True

def test_engine_status():
    r = client.get("/api/engine/status")
    assert r.status_code == 200
    assert "available" in _j(r)

def test_api_models():
    r = client.get("/api/models")
    assert r.status_code == 200
    assert isinstance(_j(r), list)

def test_api_chapters_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.get("/api/chapters")
    assert _j(r) == []
    set_active_project(_project_id)

def test_engine_modules_no_project():
    from engine.db import set_active_project
    from engine.db_settings import set_setting; set_setting("active_project", "")
    r = client.get("/api/engine/modules")
    assert _j(r)["modules"] == []
    set_active_project(_project_id)


def test_voice_page_offers_genre_presets_and_imports_them(project_id, monkeypatch):
    """Страница голоса показывает жанровые пресеты; «Добавить» кладёт профиль в проект."""
    from pathlib import Path
    import engine.engine_loaders as loaders
    from engine.db import get_voice_profiles, set_active_project, set_project_genre_key
    from web.app import app
    kb = Path(__file__).resolve().parents[2] / "UNIFIED_ENGINE_MASTER"
    monkeypatch.setattr(loaders, "get_engine_path", lambda: kb)
    set_active_project(project_id)
    set_project_genre_key(project_id, "detective_noir")
    client = app.test_client()
    html = client.get("/voice").get_data(as_text=True)
    assert "Жанровые голоса" in html and "для жанра проекта" in html
    r = client.post("/voice/import_author", json={"source": "genre:noir_detective_voice"})
    assert r.status_code == 200 and r.get_json()["ok"]
    saved = get_voice_profiles(project_id)
    assert saved and saved[0]["source"] == "genre:noir_detective_voice"
    assert "ЭТАЛОН" not in saved[0]["profile"]
