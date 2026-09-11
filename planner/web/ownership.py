"""
Принадлежность объектов текущему проекту.

Планировщик берёт идентификаторы прямо из запроса. Пока проверка стояла
на трёх обработчиках из одиннадцати, остальные позволяли править чужой
проект, просто подобрав номер: переставить сцены, откатить сцену
снапшотом, удалить акт, вписать и удалить связь.

Для одного пользователя за одним столом это незаметно, но
`PLANNER_HOST=0.0.0.0` в проекте предусмотрен, а входа нет.

Здесь собраны все проверки разом — чтобы новый обработчик брал готовую
и не изобретал свою. Поимённые заплатки в отдельных функциях как раз и
привели к тому, что закрыли три случая вместо класса.
"""

from flask import jsonify, session


def current_pid() -> int | None:
    return session.get("project_id")


def owned_scene(scene_id) -> dict | None:
    """Сцена текущего проекта — или None."""
    from engine.db import get_scene
    scene = get_scene(scene_id) if scene_id is not None else None
    pid = current_pid()
    return scene if scene and pid and scene["project_id"] == pid else None


def owned_act(act_id) -> dict | None:
    """Акт текущего проекта — или None."""
    from engine.db import get_acts
    pid = current_pid()
    if not pid or act_id is None:
        return None
    return next((a for a in get_acts(pid) if a["id"] == int(act_id)), None)


def owned_link(link_id) -> dict | None:
    """Связь текущего проекта — или None."""
    from engine.db import get_links
    pid = current_pid()
    if not pid or link_id is None:
        return None
    return next((l for l in get_links(pid) if l["id"] == int(link_id)), None)


def owned_snapshot(scene_id, snap_id) -> dict | None:
    """Снапшот сцены текущего проекта — или None."""
    if not owned_scene(scene_id):
        return None
    from engine.db import get_snapshots
    return next((s for s in get_snapshots(scene_id) if s["id"] == int(snap_id)), None)


def deny(what: str = "Объект"):
    """Единый отказ: не раскрываем, существует ли объект в другом проекте."""
    return jsonify({"error": f"{what} не найден в текущем проекте"}), 404
