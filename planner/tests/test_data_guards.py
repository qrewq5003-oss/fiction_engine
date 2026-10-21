"""Порча данных при обычной работе (разбор планировщика 21.10, пакет A)."""
import json


def _session(client, pid):
    with client.session_transaction() as sess:
        sess["project_id"] = pid


def test_stale_tab_cannot_write_other_project(client, project_id):
    from engine.db import create_project
    other = create_project("Другая книга")
    _session(client, other)                      # в другой вкладке переключились
    r = client.post("/api/scenes/new", json={"title": "из старой вкладки"},
                    headers={"X-Planner-Project": str(project_id)})
    assert r.status_code == 409 and r.get_json()["project_mismatch"]
    from engine.db import get_scenes
    assert not get_scenes(other)


def test_card_save_checks_version_and_sends_changes(client, project_id):
    from engine.db import create_scene, get_scene, update_scene
    sid = create_scene(project_id)
    update_scene(sid, {"title": "А", "notes": "заметка"})
    _session(client, project_id)
    opened = get_scene(sid)["updated_at"]
    import time
    time.sleep(1.1)
    update_scene(sid, {"notes": "правка из другой вкладки"})        # другая вкладка
    r = client.post(f"/scene/{sid}/save", json={"title": "Б", "_version": opened})
    assert r.status_code == 409 and r.get_json()["conflict"]
    assert get_scene(sid)["notes"] == "правка из другой вкладки"
    r = client.post(f"/scene/{sid}/save", json={"title": "Б", "_version": opened, "_force": True})
    assert r.status_code == 200
    s = get_scene(sid)
    assert s["title"] == "Б" and s["notes"] == "правка из другой вкладки"     # ушло только изменённое


def test_card_save_refuses_foreign_act(client, project_id):
    from engine.db import create_project, create_scene, get_acts
    other_act = get_acts(create_project("Чужая"))[0]["id"]
    sid = create_scene(project_id)
    _session(client, project_id)
    assert client.post(f"/scene/{sid}/save", json={"act_id": other_act}).status_code == 404


def test_restore_keeps_place_and_survives_deleted_act(client, project_id):
    from engine.db import create_scene, delete_act, get_acts, get_scene, get_snapshots, move_scene, update_scene
    a1, a2 = (a["id"] for a in get_acts(project_id)[:2])
    sid = create_scene(project_id, a1)
    update_scene(sid, {"title": "старое"})
    update_scene(sid, {"title": "новое"})
    move_scene(sid, a2, 0)
    delete_act(a1)
    snap = next(s for s in get_snapshots(sid) if s["data"]["title"] == "старое")
    _session(client, project_id)
    assert client.post(f"/scene/{sid}/snapshot/{snap['id']}/restore").status_code == 200
    s = get_scene(sid)
    assert s["title"] == "старое" and s["act_id"] == a2


def test_deleted_scene_goes_to_trash_and_back(client, project_id):
    from engine.db import create_scene, delete_scene, get_scene, get_trash, save_link, update_scene
    s1, s2 = create_scene(project_id), create_scene(project_id)
    update_scene(s1, {"title": "Подвал"})
    save_link(s1, s2, "cause")
    delete_scene(s1)
    assert get_scene(s1) is None
    trash = get_trash(project_id)
    assert trash[0]["title"] == "Подвал"
    _session(client, project_id)
    r = client.post(f"/api/scenes/trash/{trash[0]['id']}/restore").get_json()
    new = get_scene(r["id"])
    assert new["title"] == "Подвал" and not get_trash(project_id)
    from engine.db import get_links
    assert any(l["from_id"] == r["id"] and l["to_id"] == s2 for l in get_links(project_id))


def test_drag_puts_scene_where_dropped_and_renumbers(project_id):
    from engine.db import create_scene, get_acts, get_scene, get_snapshots, move_scene
    a1, a2 = (a["id"] for a in get_acts(project_id)[:2])
    x, y, z = (create_scene(project_id, a1) for _ in range(3))
    w = create_scene(project_id, a2)
    move_scene(z, a1, 0)                                   # в начало своего акта
    assert [get_scene(i)["position"] for i in (z, x, y)] == [1, 2, 3]
    move_scene(x, a2, 1)                                   # после w в другой акт
    assert [get_scene(i)["position"] for i in (w, x)] == [1, 2]
    assert [get_scene(i)["position"] for i in (z, y)] == [1, 2]     # прежний акт без дыр
    assert not get_snapshots(x)                             # перенос — не версия текста


def test_scenes_without_act_get_distinct_positions(project_id):
    from engine.db import create_scene, get_scene
    a, b = create_scene(project_id), create_scene(project_id)
    assert get_scene(a)["position"] != get_scene(b)["position"]


def test_acts_swap_numbers_in_one_save(client, project_id):
    from engine.db import get_acts
    acts = get_acts(project_id)
    _session(client, project_id)
    body = [{**acts[0], "number": 2}, {**acts[1], "number": 1}, acts[2],
            {"id": None, "number": 4, "title": "Эпилог", "color": "#123456"}]
    assert client.post("/api/acts/save_all", json={"acts": body}).status_code == 200
    got = {a["title"]: a["number"] for a in get_acts(project_id)}
    assert got[acts[0]["title"]] == 2 and got[acts[1]["title"]] == 1 and got["Эпилог"] == 4
    bad = client.post("/api/acts/save_all", json={"acts": [{**acts[0], "number": 1}, {**acts[1], "number": 1}]})
    assert bad.status_code == 400


def test_relinking_returns_real_link_id(project_id):
    from engine.db import create_scene, get_links, save_link
    a, b = create_scene(project_id), create_scene(project_id)
    first = save_link(a, b, "cause")
    again = save_link(a, b, "mirror")
    assert first == again != 0 and get_links(project_id)[0]["link_type"] == "mirror"


def test_reimport_can_replace_chapter_scenes(client, project_id):
    from engine.db import get_scenes, get_trash
    _session(client, project_id)
    body = {"chapter_num": 3, "act_id": None, "scenes": [{"title": "Сцена А"}], "links": []}
    client.post("/api/chapter_import/save", json=body)
    client.post("/api/chapter_import/save", json={**body, "scenes": [{"title": "Сцена Б"}], "replace": True})
    titles = [s["title"] for s in get_scenes(project_id) if s.get("chapter_num") == 3]
    assert titles == ["Сцена Б"] and get_trash(project_id)[0]["title"] == "Сцена А"


def test_bad_input_is_json_not_500_page(client, project_id):
    _session(client, project_id)
    r = client.post("/api/scenes/reorder", json={"act_id": None, "order": [{"scene_id": 1}]})
    assert r.status_code in (400, 404) and r.is_json
    assert client.post("/scene/1/save", json={"act_id": "abc"}).status_code == 404


def test_session_key_is_persistent(tmp_path, monkeypatch):
    import app as planner_app
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
    monkeypatch.setenv("PLANNER_SECRET_FILE", str(tmp_path / "k"))
    assert planner_app._session_secret() == planner_app._session_secret() == (tmp_path / "k").read_text()
    monkeypatch.setenv("FLASK_SECRET_KEY", "из-env")
    assert planner_app._session_secret() == "из-env"


def test_delete_other_project_keeps_session(client, project_id):
    from engine.db import create_project
    other = create_project("Лишний")
    _session(client, project_id)
    client.post(f"/projects/{other}/delete")
    with client.session_transaction() as sess:
        assert sess["project_id"] == project_id
