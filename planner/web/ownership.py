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


def owned_scene(scene_id: object) -> dict | None:
    """Сцена текущего проекта — или None."""
    from engine.db import get_scene
    sid = _as_id(scene_id)
    scene = get_scene(sid) if sid is not None else None
    pid = current_pid()
    return scene if scene and pid and scene["project_id"] == pid else None


def _as_id(v: object) -> int | None:
    """Номер из запроса; не число — None (было ValueError и 500)."""
    try:
        return int(v)        # type: ignore[call-overload]
    except (TypeError, ValueError):
        return None


def owned_act(act_id: object) -> dict | None:
    """Акт текущего проекта — или None."""
    from engine.db import get_acts
    pid = current_pid()
    aid = _as_id(act_id)
    if not pid or aid is None:
        return None
    return next((a for a in get_acts(pid) if a["id"] == aid), None)


def owned_link(link_id: object) -> dict | None:
    """Связь текущего проекта — или None."""
    from engine.db import get_links
    pid = current_pid()
    lid = _as_id(link_id)
    if not pid or lid is None:
        return None
    return next((l for l in get_links(pid) if l["id"] == lid), None)


def owned_snapshot(scene_id: object, snap_id: object) -> dict | None:
    """Снапшот сцены текущего проекта — или None."""
    if not owned_scene(scene_id):
        return None
    from engine.db import get_snapshots
    return next((s for s in get_snapshots(scene_id) if s["id"] == int(snap_id)), None)


def deny(what: str = "Объект") -> tuple:
    """Единый отказ: не раскрываем, существует ли объект в другом проекте."""
    return jsonify({"error": f"{what} не найден в текущем проекте"}), 404
