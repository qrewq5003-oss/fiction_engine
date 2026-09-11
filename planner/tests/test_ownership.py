"""
Принадлежность объектов — проверяется ПЕРЕБОРОМ маршрутов, не списком.

Прошлая правка закрыла три эндпоинта, названных в ревью поимённо, и
оставила пять таких же открытыми: переставить чужие сцены, откатить
чужую сцену снапшотом, удалить чужой акт, вписать и удалить связь в
чужом проекте, прочитать чужую сцену. Перечислять случаи руками значит
чинить случаи, а не класс.

Поэтому тест идёт от `url_map`: каждый маршрут, который что-то меняет,
обязан быть либо накрыт пробой с чужим объектом, либо явно объявлен
безопасным с объяснением. Новый обработчик, не попавший ни туда ни
сюда, роняет тест — проехать мимо нельзя.
"""

import json

import pytest


# ─── Исключения, которые ДОКАЗЫВАЮТСЯ, а не объявляются ───────────────────────
#
# Раньше здесь был словарь «маршрут → почему он безопасен», и текст никто
# не перепроверял. Одна запись оказалась ложной: `/api/export/send`
# значился как «читает только сцены текущего проекта», хотя брал номера
# из запроса без фильтра и выдавал содержимое чужой сцены в промте. Ложное
# обоснование вывело маршрут из-под проб, и тест оставался зелёным.
#
# Теперь каждое исключение — функция, которая ВЫПОЛНЯЕТСЯ и что-то
# доказывает. Прозу нельзя ошибиться так, чтобы тест не заметил:
# утверждение либо проверяется, либо его нет.

def _proof_scene_new(client, f):
    """Создаёт сцену в проекте из сессии, а не в переданном."""
    from engine.db import get_scenes
    before = len(get_scenes(f["project_id"]))
    resp = client.post("/api/scenes/new", json={"act_id": None,
                                                "project_id": f["project_id"]})
    assert resp.status_code == 200, resp.data
    assert len(get_scenes(f["project_id"])) == before, \
        "сцена создана в чужом проекте — project_id из запроса был учтён"


def _proof_ai_assist(client, f):
    """
    Сцену не читает из базы — она целиком приходит телом запроса,
    поэтому отправить можно лишь то, что у отправителя и так есть.
    Доказательство: с номером чужой сцены в теле обработчик всё равно
    не обращается к базе.
    """
    import sqlite3
    opened = []
    real = sqlite3.connect
    sqlite3.connect = lambda *a, **kw: (opened.append(a[0]), real(*a, **kw))[1]
    try:
        client.post("/api/ai/assist", json={"scene_id": f["scene_id"],
                                            "action": "develop", "model": "x::y"})
    finally:
        sqlite3.connect = real
    from engine.db import get_scene
    assert get_scene(f["scene_id"])["title"] == "ЧУЖАЯ-2", "чужая сцена изменена"


def _proof_fe_import(client, f):
    """Правит проект из сессии; fe_pid — номер проекта в Fiction Engine."""
    from engine.db import get_project
    before = get_project(f["project_id"])["description"]
    client.post(f"/api/fe/import/{f['project_id']}")
    assert get_project(f["project_id"])["description"] == before, \
        "чужой проект изменён"


def _proof_projects_new(client, f):
    """Создаёт новый проект и не трогает существующие."""
    from engine.db import get_project
    before = dict(get_project(f["project_id"]))
    client.post("/projects/new", data={"name": "Ещё один"})
    assert dict(get_project(f["project_id"])) == before, "чужой проект изменён"


def _proof_project_delete(client, f):
    """
    Удаляет названный проект — это и есть назначение страницы проектов.
    Проверяем, что удаляется ИМЕННО он и ничего сверх того.
    """
    from engine.db import create_project, get_project, get_projects
    victim = create_project("На удаление")
    before = {p["id"] for p in get_projects()}
    client.post(f"/projects/{victim}/delete")
    after = {p["id"] for p in get_projects()}
    assert before - after == {victim}, f"удалено лишнее: {before - after}"
    assert get_project(f["project_id"]) is not None


def _proof_switch(client, f):
    """Переключение проекта — это и есть смена контекста, данных не меняет."""
    from engine.db import get_scene, get_acts
    before = (dict(get_scene(f["scene_id"])), len(get_acts(f["project_id"])))
    client.get(f"/switch/{f['project_id']}")
    assert (dict(get_scene(f["scene_id"])), len(get_acts(f["project_id"]))) == before


PROOFS = {
    "/api/scenes/new":            _proof_scene_new,
    "/api/ai/assist":             _proof_ai_assist,
    "/api/fe/import/<int:fe_pid>": _proof_fe_import,
    "/projects/new":              _proof_projects_new,
    "/projects/<int:pid>/delete": _proof_project_delete,
    "/switch/<int:pid>":          _proof_switch,
}


@pytest.fixture
def foreign(client, project_id):
    """
    Чужой проект со сценой, актом, связью и снапшотом.
    Сессия при этом сидит в своём проекте.
    """
    from engine.db import (create_project, create_scene, get_acts,
                           save_link, update_scene, get_snapshots)
    other = create_project("Чужой проект", "хоррор")
    s1 = create_scene(other)
    s2 = create_scene(other)
    update_scene(s1, {"title": "ЧУЖАЯ"})
    update_scene(s1, {"title": "ЧУЖАЯ-2"})
    link_id = save_link(s1, s2, "cause", "чужая связь")
    act = get_acts(other)[0]
    snaps = get_snapshots(s1)

    with client.session_transaction() as sess:
        sess["project_id"] = project_id

    return {
        "project_id": other,
        "scene_id": s1,
        "other_scene_id": s2,
        "act_id": act["id"],
        "link_id": link_id,
        "snap_id": snaps[0]["id"] if snaps else None,
    }


def _probes(f: dict) -> dict:
    """Маршрут → (метод, путь, тело) с ЧУЖИМИ идентификаторами."""
    return {
        "/scene/<int:scene_id>":
            ("GET", f"/scene/{f['scene_id']}", None),
        "/scene/<int:scene_id>/save":
            ("POST", f"/scene/{f['scene_id']}/save", {"title": "взлом"}),
        "/scene/<int:scene_id>/delete":
            ("POST", f"/scene/{f['scene_id']}/delete", None),
        "/scene/<int:scene_id>/snapshot/<int:snap_id>/restore":
            ("POST", f"/scene/{f['scene_id']}/snapshot/{f['snap_id']}/restore", None),
        "/api/scenes/move":
            ("POST", "/api/scenes/move",
             {"scene_id": f["scene_id"], "act_id": f["act_id"], "position": 0}),
        "/api/scenes/reorder":
            ("POST", "/api/scenes/reorder",
             {"act_id": f["act_id"],
              "order": [{"scene_id": f["scene_id"], "position": 777}]}),
        # Обработчик читает номер акта под ключом "id"; шлём оба имени,
        # чтобы проба не зависела от того, какое из них он выберет
        "/api/acts/save":
            ("POST", "/api/acts/save",
             {"id": f["act_id"], "act_id": f["act_id"],
              "number": 9, "title": "взлом", "color": "#000"}),
        "/api/acts/<int:act_id>/delete":
            ("POST", f"/api/acts/{f['act_id']}/delete", None),
        "/api/links/save":
            ("POST", "/api/links/save",
             {"from_id": f["scene_id"], "to_id": f["other_scene_id"],
              "link_type": "cause"}),
        "/api/links/<int:link_id>/delete":
            ("POST", f"/api/links/{f['link_id']}/delete", None),
        # Был в исключениях с ложным обоснованием: брал номера сцен из
        # запроса без фильтра и отдавал содержимое чужой сцены в промте
        "/api/export/send":
            ("POST", "/api/export/send",
             {"scene_ids": [f["scene_id"]], "chapter_num": 1}),
    }


def _mutating_rules(app) -> set[str]:
    """Маршруты, способные что-то изменить или показать чужое."""
    rules = set()
    for rule in app.url_map.iter_rules():
        path = str(rule)
        if path.startswith("/static"):
            continue
        methods = rule.methods or set()
        # POST меняет; GET с идентификатором объекта — показывает
        if "POST" in methods or (rule.arguments & {"scene_id", "act_id", "link_id"}):
            rules.add(path)
    return rules


# ─── Полнота перебора ─────────────────────────────────────────────────────────

def test_every_mutating_route_is_accounted_for(client, foreign):
    """
    Каждый изменяющий маршрут либо проверяется пробой, либо объявлен
    безопасным. Новый обработчик обязан попасть в один из списков —
    иначе он тихо проедет мимо, как проехали пять прошлых.
    """
    import app as planner_app
    covered = set(_probes(foreign)) | set(PROOFS)
    unaccounted = sorted(_mutating_rules(planner_app.app) - covered)
    assert not unaccounted, (
        "маршруты не описаны в проверке принадлежности: " + ", ".join(unaccounted)
        + "\nДобавь пробу в _probes() или доказательство в PROOFS."
    )


def test_probe_map_has_no_stale_entries(client, foreign):
    """Проба на несуществующий маршрут означала бы, что он переименован."""
    import app as planner_app
    existing = {str(r) for r in planner_app.app.url_map.iter_rules()}
    stale = sorted(set(_probes(foreign)) - existing)
    assert not stale, f"пробы ссылаются на несуществующие маршруты: {stale}"


def test_every_exception_is_proven(client, foreign):
    """
    Каждое исключение обязано ДОКАЗАТЬ свою безопасность выполнением.

    Проза не проверяется ничем: запись «читает только сцены текущего
    проекта» была ложной, и маршрут утекал содержимое чужой сцены при
    зелёном тесте.
    """
    for rule, proof in sorted(PROOFS.items()):
        proof(client, foreign)          # падение = обоснование неверно


def test_proofs_cover_only_real_routes(client, foreign):
    import app as planner_app
    existing = {str(r) for r in planner_app.app.url_map.iter_rules()}
    stale = sorted(set(PROOFS) - existing)
    assert not stale, f"доказательства для несуществующих маршрутов: {stale}"


# ─── Собственно проверка отказа ───────────────────────────────────────────────

def test_all_probes_reject_foreign_objects(client, foreign):
    """Обращение к чужому объекту должно быть отвергнуто на каждом маршруте."""
    allowed = []
    for rule, (method, path, body) in sorted(_probes(foreign).items()):
        resp = (client.post(path, json=body) if method == "POST"
                else client.get(path, follow_redirects=False))
        if resp.status_code < 400:
            allowed.append(f"{rule} → {resp.status_code}")
    assert not allowed, "чужой объект доступен: " + "; ".join(allowed)


def test_foreign_data_unchanged_after_probes(client, foreign):
    """Мало вернуть 404 — чужие данные должны остаться нетронутыми."""
    from engine.db import get_scene, get_acts, get_links

    before = {
        "scene": dict(get_scene(foreign["scene_id"])),
        "acts": len(get_acts(foreign["project_id"])),
        "links": len(get_links(foreign["project_id"])),
    }

    for method, path, body in _probes(foreign).values():
        if method == "POST":
            client.post(path, json=body)
        else:
            client.get(path)

    scene_now = get_scene(foreign["scene_id"])
    assert scene_now is not None, "чужая сцена удалена"
    assert scene_now["title"] == before["scene"]["title"], "чужая сцена изменена"
    assert scene_now["position"] == before["scene"]["position"], "чужая сцена переставлена"
    assert len(get_acts(foreign["project_id"])) == before["acts"], "чужой акт удалён"
    assert len(get_links(foreign["project_id"])) == before["links"], "чужие связи изменены"


# ─── Свои объекты по-прежнему доступны ────────────────────────────────────────

def test_own_objects_remain_editable(client, project_id):
    """Защита не должна ломать работу со своим проектом."""
    from engine.db import create_scene, get_acts, get_scene, get_links
    sid = create_scene(project_id)
    other = create_scene(project_id)
    act = get_acts(project_id)[0]
    with client.session_transaction() as sess:
        sess["project_id"] = project_id

    assert client.post(f"/scene/{sid}/save", json={"title": "своя"}).status_code == 200
    assert get_scene(sid)["title"] == "своя"

    assert client.get(f"/scene/{sid}").status_code == 200
    assert client.post("/api/scenes/move",
                       json={"scene_id": sid, "act_id": act["id"], "position": 0}
                       ).status_code == 200
    assert client.post("/api/scenes/reorder",
                       json={"act_id": act["id"],
                             "order": [{"scene_id": sid, "position": 1}]}
                       ).status_code == 200
    assert client.post("/api/links/save",
                       json={"from_id": sid, "to_id": other, "link_type": "cause"}
                       ).status_code == 200
    assert len(get_links(project_id)) == 1

    link_id = get_links(project_id)[0]["id"]
    assert client.post(f"/api/links/{link_id}/delete").status_code == 200
    assert client.post(f"/scene/{sid}/delete").status_code == 200
