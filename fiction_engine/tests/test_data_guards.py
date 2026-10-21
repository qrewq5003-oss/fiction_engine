"""Порча данных при обычной работе (разбор 21.10, группа 1)."""
import json


def _client(project_id):
    from engine.db_settings import set_active_project
    from web.app import app
    set_active_project(project_id)
    app.config.update(TESTING=True, FE_CSRF=False)
    return app.test_client()


def test_state_form_does_not_overwrite_chapter_changes(project_id):
    """Форма State, открытая до «Принять», не перетирает вписанное главой молча."""
    from engine.db import get_state
    from engine.db_state import update_state
    from web.blueprints.state_bp import state_version
    update_state(project_id, global_state="## ПЕРСОНАЖИ\n### Вера\nСОСТОЯНИЕ: до главы\n")
    opened = state_version(get_state(project_id))
    update_state(project_id, global_state="## ПЕРСОНАЖИ\n### Вера\nСОСТОЯНИЕ: после главы 5\n")  # «Принять»
    c = _client(project_id)
    form = {"state_version": opened, "global_state": "правка автора", "plot_matrix": "", "memory_graph": ""}
    r = c.post("/state/edit", data=form)
    assert r.status_code == 409 and "после главы 5" in get_state(project_id)["global_state"]
    assert "правка автора" in r.get_data(as_text=True)                    # правки не потеряны
    form["state_version"] = state_version(get_state(project_id))          # «Сохранить» ещё раз — сознательно
    assert c.post("/state/edit", data=form).status_code == 302
    assert get_state(project_id)["global_state"] == "правка автора"


def test_pages_send_project_and_do_not_restore_state(project_id):
    c = _client(project_id)
    state_html = c.get("/state").get_data(as_text=True)
    assert f'<meta name="fe-project" content="{project_id}">' in state_html
    assert 'id="ta-global" data-nopersist' in state_html and 'name="state_version"' in state_html
    pipe = c.get("/pipeline").get_data(as_text=True)
    assert f"'ps_{project_id}_' + key" in pipe and "state.currentText = merged;" in pipe
    assert 'data-nopersist' in c.get("/prep").get_data(as_text=True)


def test_stale_tab_form_is_refused(project_id):
    from engine.db import get_state
    from engine.db_projects import create_project
    from engine.db_state import update_state
    update_state(project_id, global_state="книга A")
    c = _client(project_id)
    other = create_project("Книга B", "детектив")
    r = c.post("/state/edit", data={"fe_project": str(other), "global_state": "чужое"})
    assert r.status_code == 409 and get_state(project_id)["global_state"] == "книга A"


def test_rewritten_chapter_keeps_closures_by_later_chapters(project_id):
    """«Фон»: 38 из 148 обещаний закрыты поздними главами — новый L3 главы их снова открывал."""
    from engine.db import get_l3_summary, save_chapter, save_l3_summary
    from engine.db_chapters import forget_chapter_text
    from engine.l3_memory import generate_l3_summary
    save_chapter(project_id, 2, "Глава два. " * 30, "Глава 2")
    save_l3_summary(project_id, 2, {"events": "гл.2", "promises": [
        {"id": "2_0", "text": "Кто вынес микшерный пульт из подсобки театра", "resolved": True, "resolved_chapter": 5},
        {"id": "2_1", "text": "Почему Артём вырвал страницу журнала", "resolved": False, "resolved_chapter": None}]})
    answer = json.dumps({"events": "гл.2 заново", "characters": "", "conflicts": "", "mood": "",
                         "promises": [{"text": "Кто именно вынес микшерный пульт из подсобки"},
                                      {"text": "Почему Артём вырвал страницу из журнала"}]}, ensure_ascii=False)
    # Кнопка L3 — поверх прежнего саммари
    generate_l3_summary(project_id, 2, "Глава два. " * 30, lambda p: answer)
    ps = get_l3_summary(project_id, 2)["promises"]
    assert ps[0]["resolved"] and ps[0]["resolved_chapter"] == 5 and not ps[1]["resolved"]
    # Пересчёт: L3 удаляется (forget_chapter_text), закрытие откладывается и возвращается
    forget_chapter_text(project_id, 2)
    assert get_l3_summary(project_id, 2) is None
    generate_l3_summary(project_id, 2, "Глава два. " * 30, lambda p: answer)
    ps = get_l3_summary(project_id, 2)["promises"]
    assert ps[0]["resolved_chapter"] == 5 and not ps[1]["resolved"]
