"""
Библия серии через API — для планировщика (web/blueprints/generate_narrative.py).
"""


def _client():
    from web.app import app
    return app.test_client()


def test_bible_set_and_get_by_pid(project_id):
    c = _client()
    r = c.post("/api/bible/set", json={"pid": project_id, "kind": "место", "name": "квартира Ларионовой",
                                       "attr": "этаж", "value": "второй"})
    assert r.status_code == 200
    c.post("/api/bible/set", json={"pid": project_id, "kind": "место", "name": "квартира Ларионовой",
                                   "attr": "этаж", "value": "пятый", "chapter_num": 9,
                                   "reason": "переехала к сестре"})
    d = c.get(f"/api/bible?pid={project_id}").get_json()
    assert [f["value"] for f in d["facts"]] == ["пятый"]
    assert [h["value"] for h in d["history"]] == ["второй", "пятый"]      # прошлое не перезаписано


def test_bible_errors(project_id):
    c = _client()
    assert c.get("/api/bible?pid=99999").status_code == 404
    assert c.post("/api/bible/set", json={"pid": project_id, "name": "x"}).status_code == 400


def test_chapter_plan_saves_note_and_facts(project_id):
    from engine.db import get_director_note
    from engine.series_bible import current
    c = _client()
    r = c.post("/api/chapter_plan/4/save", json={
        "pid": project_id, "note": "ПЛАН ГЛАВЫ 4\nСЦЕНА 1: допрос",
        "facts": [{"kind": "событие", "name": "глава 4, сцена 1: допрос", "attr": "место",
                   "value": "контора на Литейном"},
                  {"kind": "событие", "name": "глава 4, сцена 1: допрос", "attr": "время", "value": "вечер"},
                  "мусор"]})
    assert r.get_json() == {"ok": True, "facts": 2}
    assert "допрос" in get_director_note(project_id, 4)
    got = {(f["attr"], f["value"]) for f in current(project_id)}
    assert got == {("место", "контора на Литейном"), ("время", "вечер")}
    assert c.post("/api/chapter_plan/4/save", json={"pid": project_id, "note": ""}).status_code == 400
