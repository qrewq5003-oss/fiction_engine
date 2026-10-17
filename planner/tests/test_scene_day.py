"""
День сцены (миграция 6). Время суток — выпадающий список, и проверке времени
(engine/timeline) не из чего было взять день: в книге-прогоне 17.10 дни
уезжали от плана, а подсказок не было ни одной.
"""


def _session(client, pid):
    with client.session_transaction() as sess:
        sess["project_id"] = pid


def test_day_is_saved_and_shown(client, project_id):
    from engine.db import create_scene, get_scene
    sid = create_scene(project_id)
    _session(client, project_id)
    client.post(f"/scene/{sid}/save", json={"title": "Паром", "day": "пятница, 24 октября",
                                            "time_of_day": "Утро"})
    assert get_scene(sid)["day"] == "пятница, 24 октября"
    assert 'value="пятница, 24 октября"' in client.get(f"/scene/{sid}").get_data(as_text=True)
    assert "пятница, 24 октября, утро" in client.get("/board").get_data(as_text=True)


def test_old_free_time_value_survives_the_select(client, project_id):
    """Прежнее «утро понедельника» в выпадающем списке не превращается в «не указано»."""
    from engine.db import create_scene, update_scene
    sid = create_scene(project_id)
    update_scene(sid, {"title": "x", "time_of_day": "утро понедельника"})
    _session(client, project_id)
    page = client.get(f"/scene/{sid}").get_data(as_text=True)
    assert '<option value="утро понедельника" selected>' in page


def test_timeline_reads_day_with_time_of_day():
    from engine.timeline import check, scene_when
    assert scene_when({"day": "пятница", "time_of_day": "Вечер"}) == "пятница, вечер"
    assert scene_when({"time_of_day": "Утро"}) == "Утро"
    warns = check([{"id": 1, "title": "Паром", "day": "пятница, 24 октября", "time_of_day": "Утро"},
                   {"id": 2, "title": "Ужин", "day": "пятница, 24 октября", "time_of_day": "Вечер"},
                   {"id": 3, "title": "Записка", "day": "23 октября", "time_of_day": "Ночь"}])
    assert [w["scene_id"] for w in warns] == [3] and "раньше" in warns[0]["message"]


def test_plan_and_bible_get_the_day(client, project_id, monkeypatch):
    import requests
    from engine.db import create_scene, set_fe_project, update_scene
    sent = {}

    class Resp:
        ok = True
        def json(self): return {"facts": 3}

    monkeypatch.setattr(requests, "post", lambda url, json=None, **k: (sent.update(json or {}), Resp())[1])
    sid = create_scene(project_id)
    update_scene(sid, {"title": "Тело у маяка", "location": "маяк", "day": "пятница, 24 октября",
                       "time_of_day": "Утро"})
    set_fe_project(project_id, 6)
    _session(client, project_id)
    client.post("/api/export/send", json={"scene_ids": [sid], "chapter_num": 1})
    assert "Когда: пятница, 24 октября, утро" in sent["note"]
    assert {"kind": "событие", "name": "глава 1, сцена 1: Тело у маяка", "attr": "время",
            "value": "пятница, 24 октября, утро"} in sent["facts"]
