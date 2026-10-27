"""Связка с планировщиком (разбор планировщика 21.10, пакет B) — сторона FE."""


def test_own_plan_facts_go_to_analysis_not_twice_to_writer(project_id):
    """Факты плана главы N — анализу главы N (срез «до главы N» их выбрасывал, и «текст
    важнее плана» не срабатывал). Писателю и проверке непрерывности главы N — нет: план
    они получают целиком, и сцена шла дважды (разбор формулировок 26.10). Главе N+1 —
    да, это уже прошлое."""
    from engine.series_bible import PLAN_REASON, author_set, bible_block, current, known_for_analysis
    author_set(project_id, "событие", "глава 5, сцена 1: Подвал", "место", "подвал театра", 5,
               PLAN_REASON.format(5))
    author_set(project_id, "событие", "глава 6, сцена 1: Крыша", "место", "крыша", 6, PLAN_REASON.format(6))
    names = {r["name"] for r in current(project_id, 5)}
    assert "глава 5, сцена 1: Подвал" in names and "глава 6, сцена 1: Крыша" not in names
    assert "Подвал" in known_for_analysis(project_id, 5, "Они спустились в подвал.")
    assert "подвал театра" not in bible_block(project_id, "подвал", before_chapter=5)
    assert "подвал театра" in bible_block(project_id, "подвал", before_chapter=6)


def test_future_uses_fresh_plans_of_later_chapters(project_id):
    from engine.db_narrative import save_director_note
    from engine.run_ahead import get_future, save_future
    save_future(project_id, 12, "- гл.15 «Старое»: Вера находит нож\n- дальше «Финал»: признание")
    assert "находит нож" in get_future(project_id, 12)
    save_director_note(project_id, 14, "ПЛАН ГЛАВЫ 15\n\nСЦЕНА 1: Новое — Вера теряет ключ")
    fut = get_future(project_id, 12)
    assert "находит нож" not in fut and "теряет ключ" in fut and "признание" in fut


def test_project_context_at_chapter_and_focus(project_id):
    from engine.db import save_chapter
    from engine.db_settings import set_active_project
    from engine.db_state import update_state
    from web.app import app
    for n in (1, 2, 3):
        save_chapter(project_id, n, f"Глава {n}. " * 40, f"Глава {n}")
    update_state(project_id, global_state="## ПЕРСОНАЖИ\n### Вера\nРОЛЬ: медсестра\n### Дина\nРОЛЬ: санитарка\n")
    set_active_project(project_id)
    app.config.update(TESTING=True, FE_CSRF=False)
    c = app.test_client()
    assert c.get(f"/api/project/context?pid={project_id}&chapter=2").status_code == 200
    d = c.post("/api/project/scene_context", json={"pid": project_id, "chapter": 2, "focus": "Вера на посту"}).get_json()
    assert "Вера" in d["state_focus"] and "медсестра" in d["state_focus"]


def test_keys_status_lists_subscriptions(monkeypatch):
    from web.app import app
    monkeypatch.setattr("engine.db_settings.get_api_key",
                        lambda p: "claude-cli" if p == "claude_subscription" else None)
    app.config.update(TESTING=True, FE_CSRF=False)
    assert "claude_subscription" in app.test_client().get("/api/keys/status").get_json()
