"""
Что автор делает в планировщике руками — найдено прогоном по всем кнопкам 17.10:
история версий не открывалась, брошенные карточки копились на доске,
превью плана расходилось с отправленным, номер главы всегда был 1.
"""

import html
import json
import re


def _session(client, pid):
    with client.session_transaction() as sess:
        sess["project_id"] = pid


# ─── История версий ───────────────────────────────────────────────────────────

def test_snapshot_only_when_something_changes(project_id):
    from engine.db import create_scene, get_snapshots, update_scene
    sid = create_scene(project_id)
    update_scene(sid, {"title": "Больница", "act_id": None})
    update_scene(sid, {"title": "Больница", "act_id": None})     # автосохранение при уходе
    update_scene(sid, {"title": "Больница ", "notes": None})      # те же значения
    assert len(get_snapshots(sid)) == 1
    update_scene(sid, {"title": "Больница утром"})
    assert len(get_snapshots(sid)) == 2


def test_history_preview_attribute_survives_json_quotes(client, project_id):
    """JSON версии в onclick="…" обрывал атрибут: окно версии не открывалось."""
    from engine.db import create_scene, update_scene
    sid = create_scene(project_id)
    update_scene(sid, {"title": 'Сцена "в кавычках"', "what_happens": "Павел — с кофе"})
    update_scene(sid, {"title": "Другая"})
    _session(client, project_id)
    page = client.get(f"/scene/{sid}").get_data(as_text=True)
    m = re.search(r"onclick='previewSnap\((\d+), (.*?)\)'", page)
    assert m, "атрибут истории не в одинарных кавычках"
    data = json.loads(html.unescape(m.group(2)))
    assert data["title"] == 'Сцена "в кавычках"'


# ─── Новая карточка ───────────────────────────────────────────────────────────

def test_new_card_is_not_saved_until_author_saves(client, project_id):
    from engine.db import get_acts, get_scenes, get_snapshots
    _session(client, project_id)
    act = get_acts(project_id)[0]
    page = client.get(f"/scene/new?act={act['id']}")
    assert page.status_code == 200
    assert "let SCENE_ID = null" in page.get_data(as_text=True)
    assert get_scenes(project_id) == []

    r = client.post("/api/scenes/new", json={"act_id": act["id"], "title": "Больница",
                                             "location": "палата", "time_of_day": "Утро"}).get_json()
    scene = next(s for s in get_scenes(project_id) if s["id"] == r["id"])
    assert (scene["title"], scene["act_id"], scene["time_of_day"]) == ("Больница", act["id"], "Утро")
    assert get_snapshots(r["id"]) == []          # к пустой карточке откатываться незачем


def test_new_scene_in_foreign_act_rejected(client, project_id):
    from engine.db import create_project, get_acts, get_scenes
    other = create_project("Чужой")
    _session(client, project_id)
    r = client.post("/api/scenes/new", json={"act_id": get_acts(other)[0]["id"], "title": "x"})
    assert r.status_code == 404
    assert get_scenes(project_id) == [] and get_scenes(other) == []


def test_missing_scene_page_is_readable(client, project_id):
    _session(client, project_id)
    r = client.get("/scene/99999")
    assert r.status_code == 404
    text = r.get_data(as_text=True)
    assert "не найдена" in text and "На доску" in text


# ─── Экспорт плана ────────────────────────────────────────────────────────────

def _scenes(project_id):
    from engine.db import create_scene, update_scene
    a, b = create_scene(project_id), create_scene(project_id)
    update_scene(a, {"title": "Больница", "location": "палата", "time_of_day": "Утро",
                     "characters": "Лукаш, врач", "what_happens": "Видит линии.",
                     "notes": "черновик: проверить имя врача"})
    update_scene(b, {"title": "Коридор", "time_of_day": "День"})
    return a, b


def test_plan_text_skips_notes_and_empty_time(project_id):
    from engine.db import get_scene
    from web.blueprints.api_bp import plan_text
    a, b = _scenes(project_id)
    t = plan_text([get_scene(a), get_scene(b)], 2)
    assert t.startswith("ПЛАН ГЛАВЫ 2")
    assert "Локация: палата / Утро" in t and "Время: День" in t
    assert "черновик" not in t and "Заметки" not in t


def test_preview_is_what_gets_sent(client, project_id, monkeypatch):
    import requests
    sent = {}

    class Resp:
        ok = True
        def json(self): return {"facts": 0}

    monkeypatch.setattr(requests, "post", lambda url, json=None, **k: (sent.update(url=url, body=json), Resp())[1])
    a, b = _scenes(project_id)
    _session(client, project_id)
    preview = client.post("/api/export/preview", json={"scene_ids": [a, b], "chapter_num": 2}).get_json()
    client.post("/api/export/send", json={"scene_ids": [a, b], "chapter_num": 2})
    assert sent["body"]["note"] == preview["prompt"].strip()

    # Автор поправил план в окне — уходит его текст
    client.post("/api/export/send", json={"scene_ids": [a, b], "chapter_num": 2,
                                          "text": "ПЛАН ГЛАВЫ 2\nСЦЕНА 1: своя"})
    assert sent["body"]["note"] == "ПЛАН ГЛАВЫ 2\nСЦЕНА 1: своя"


def test_sent_plan_marks_scenes_with_chapter(client, project_id, monkeypatch):
    """Отправленный план помнит главу; новый план той же главы заменяет прежний."""
    import requests
    from engine.db import get_scene, get_snapshots

    class Resp:
        ok = True
        def json(self): return {}

    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp())
    a, b = _scenes(project_id)
    snaps = len(get_snapshots(a))
    _session(client, project_id)
    client.post("/api/export/send", json={"scene_ids": [a, b], "chapter_num": 2})
    assert (get_scene(a)["chapter_num"], get_scene(b)["chapter_num"]) == (2, 2)
    assert len(get_snapshots(a)) == snaps            # метка — не правка карточки
    client.post("/api/export/send", json={"scene_ids": [b], "chapter_num": 2})
    assert (get_scene(a)["chapter_num"], get_scene(b)["chapter_num"]) == (None, 2)
    board = client.get("/board").get_data(as_text=True)
    assert "гл.2</span> Коридор" in board


def test_export_suggests_next_chapter(client, project_id, monkeypatch):
    import io
    from engine.db import set_fe_project
    import web.blueprints.api_bp as api
    _session(client, project_id)
    assert 'value="1"' in client.get("/export").get_data(as_text=True)

    set_fe_project(project_id, 6)
    monkeypatch.setattr(api, "_fe_get", lambda path, timeout: io.BytesIO(b'{"last_chapter": 3}'))
    assert 'id="chapter-num" value="4"' in client.get("/export").get_data(as_text=True)
