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


# ─── Маршруты, которым чужой объект передать невозможно ───────────────────────
#
# Каждый работает только с текущим проектом из сессии и не принимает
# идентификатор объекта извне. Запись здесь — обещание, которое проверяется
# ниже: если маршрут начнёт принимать чужой id, он должен переехать в пробы.

SAFE_BY_DESIGN = {
    "/api/scenes/new":      "создаёт сцену в проекте из сессии",
    "/api/ai/assist":       "сверяет сцену через owned_scene",
    "/api/export/send":     "читает только сцены текущего проекта",
    "/api/fe/import/<int:fe_pid>": "правит проект из сессии, fe_pid — номер в FE",
    "/projects/new":        "создаёт новый проект",
    "/projects/<int:pid>/delete": "проекты принадлежат одному пользователю целиком",
    "/switch/<int:pid>":    "переключение проекта — это и есть смена контекста",
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
    covered = set(_probes(foreign)) | set(SAFE_BY_DESIGN)
    unaccounted = sorted(_mutating_rules(planner_app.app) - covered)
    assert not unaccounted, (
        "маршруты не описаны в проверке принадлежности: " + ", ".join(unaccounted)
        + "\nДобавь пробу в _probes() или обоснование в SAFE_BY_DESIGN."
    )


def test_probe_map_has_no_stale_entries(client, foreign):
    """Проба на несуществующий маршрут означала бы, что он переименован."""
    import app as planner_app
    existing = {str(r) for r in planner_app.app.url_map.iter_rules()}
    stale = sorted(set(_probes(foreign)) - existing)
    assert not stale, f"пробы ссылаются на несуществующие маршруты: {stale}"


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
