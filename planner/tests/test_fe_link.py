"""Связка с FE (разбор планировщика 21.10, пакет B) — сторона планировщика."""
import io
import json


def _session(client, pid):
    with client.session_transaction() as sess:
        sess["project_id"] = pid


def test_ai_help_asks_book_at_scene_chapter_with_its_heroes(client, project_id, monkeypatch):
    import web.blueprints.api_bp as api
    from engine.db import create_scene, set_fe_project, update_scene
    set_fe_project(project_id, 7)
    sid = create_scene(project_id)
    update_scene(sid, {"title": "Пост", "characters": "Вера, Дина"})
    from engine.db import get_conn
    with get_conn() as conn:
        conn.execute("UPDATE scenes SET chapter_num=5 WHERE id=?", (sid,))
    asked = []
    monkeypatch.setattr(api, "_fe_get", lambda path, timeout: (asked.append(path), io.BytesIO(json.dumps(
        {"story_so_far": "гл.4", "last_chapter": 4}).encode()))[1])
    import requests
    sent = []

    class Ok:
        ok = True
        def __init__(self, body): self.body = body
        def json(self): return self.body
        def raise_for_status(self): pass

    def post(url, json=None, **k):
        sent.append((url, json))
        if url.endswith("/api/project/scene_context"):
            return Ok({"state_focus": "### Вера\nРОЛЬ: медсестра"})
        return Ok({"result": "совет"})
    monkeypatch.setattr(requests, "post", post)
    _session(client, project_id)
    r = client.post("/api/ai/assist", json={"scene_id": sid, "action": "develop", "model": "x::y",
                                            "scene": {"title": "Пост", "characters": "Вера, Дина"}}).get_json()
    assert r["ok"] and not r.get("warning")
    assert "chapter=5" in asked[0]
    focus_req = next(b for u, b in sent if u.endswith("/api/project/scene_context"))
    assert focus_req["chapter"] == 5 and "Вера" in focus_req["focus"]
    prompt = next(b for u, b in sent if u.endswith("/api/inline_call"))["prompt"]
    assert "медсестра" in prompt


def test_status_tells_token_problem_from_fe_off(client, monkeypatch):
    import urllib.error
    import web.blueprints.api_bp as api
    def refuse(path, timeout):
        raise urllib.error.HTTPError(path, 401, "нужен вход", None, None)
    monkeypatch.setattr(api, "_fe_get", refuse)
    d = client.get("/api/status").get_json()
    assert d["fe_server"] is True and "401" in d["fe_error"] and "токен" in d["fe_error"]


def test_board_marks_stale_chapter_plan(client, project_id):
    from engine.db import create_scene, get_conn, set_chapter_scenes, set_fe_project, stale_chapter_plans, update_scene
    set_fe_project(project_id, 7)
    sid = create_scene(project_id)
    update_scene(sid, {"title": "Подвал"})
    set_chapter_scenes(project_id, 3, [sid])
    assert stale_chapter_plans(project_id) == []
    with get_conn() as conn:                               # отправлено минуту назад
        conn.execute("UPDATE chapter_exports SET exported_at=datetime('now','-1 minute')")
    update_scene(sid, {"what_happens": "правка после отправки"})
    assert stale_chapter_plans(project_id) == [3]
    _session(client, project_id)
    assert "План в Fiction Engine устарел для глав 3" in client.get("/board").get_data(as_text=True)
    set_chapter_scenes(project_id, 3, [sid])                # отправили заново
    assert stale_chapter_plans(project_id) == []


def test_export_timeout_is_not_called_unavailable(client, project_id, monkeypatch):
    import requests
    from engine.db import create_scene, set_fe_project, update_scene
    set_fe_project(project_id, 7)
    sid = create_scene(project_id)
    update_scene(sid, {"title": "Сцена"})
    def slow(*a, **k):
        raise requests.exceptions.ReadTimeout("read timed out")
    monkeypatch.setattr(requests, "post", slow)
    _session(client, project_id)
    r = client.post("/api/export/send", json={"scene_ids": [sid], "chapter_num": 2})
    d = r.get_json()
    assert r.status_code == 504 and "неизвестно, дошёл ли" in d["error"] and d["prompt"]


def test_export_warns_about_scene_in_other_chapter_plan(client, project_id, monkeypatch):
    import requests
    from engine.db import create_scene, set_chapter_scenes, set_fe_project, update_scene
    set_fe_project(project_id, 7)
    sid = create_scene(project_id)
    update_scene(sid, {"title": "Сцена"})
    set_chapter_scenes(project_id, 2, [sid])

    class Ok:
        ok = True
        def json(self): return {"facts": 1}
    monkeypatch.setattr(requests, "post", lambda *a, **k: Ok())
    _session(client, project_id)
    d = client.post("/api/export/send", json={"scene_ids": [sid], "chapter_num": 3}).get_json()
    assert d["sent"] and "плане глав 2" in d["warning"]
