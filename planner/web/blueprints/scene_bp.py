from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify

bp = Blueprint("scene", __name__)

from ..ownership import owned_act, owned_scene, owned_snapshot, deny  # noqa: E402


def current_project():
    from engine.db import get_project
    pid = session.get("project_id")
    return get_project(pid) if pid else None


@bp.route("/scene/<int:scene_id>")
def scene_detail(scene_id):
    # Страница, а не API: на удалённую или чужую сцену — страница «не
    # найдена» со ссылкой на доску. Раньше автор видел голый JSON с
    # \u-кодами вместо текста
    s = owned_scene(scene_id)
    if not s:
        return render_template("not_found.html", what="Сцена"), 404
    from engine.db import get_acts, get_snapshots
    p = current_project()
    acts      = get_acts(p["id"]) if p else []
    snapshots = get_snapshots(scene_id)
    return render_template("scene.html", scene=s, acts=acts, snapshots=snapshots)


@bp.route("/scene/new")
def scene_new_form():
    """
    Пустая карточка без записи в базе: сцена появляется при первом
    сохранении. Раньше «+ сцена» сразу создавала запись, и каждая открытая
    и брошенная карточка оставалась на доске «Без названия #N».
    """
    p = current_project()
    if not p:
        return redirect(url_for("main.projects"))
    from engine.db import get_acts
    act_id = request.args.get("act", type=int)
    if act_id is not None and not owned_act(act_id):
        act_id = None
    return render_template("scene.html", scene={"id": None, "act_id": act_id},
                           acts=get_acts(p["id"]), snapshots=[])


@bp.route("/scene/<int:scene_id>/save", methods=["POST"])
def scene_save(scene_id):
    from engine.db import update_scene
    if not owned_scene(scene_id):
        return deny("Сцена")
    data = request.json or {}
    update_scene(scene_id, data, reason="изменена")
    return jsonify({"ok": True})


@bp.route("/scene/<int:scene_id>/delete", methods=["POST"])
def scene_delete(scene_id):
    from engine.db import delete_scene
    if not owned_scene(scene_id):
        return deny("Сцена")
    delete_scene(scene_id)
    return jsonify({"ok": True})


@bp.route("/scene/<int:scene_id>/snapshot/<int:snap_id>/restore", methods=["POST"])
def snapshot_restore(scene_id, snap_id):
    # Тот же update_scene, что и в scene_save, только в обход проверки:
    # чужую сцену можно было перезаписать её же снапшотом.
    if not owned_snapshot(scene_id, snap_id):
        return deny("Снапшот")
    from engine.db import get_snapshots, update_scene
    snaps = get_snapshots(scene_id)
    snap  = next((s for s in snaps if s["id"] == snap_id), None)
    if not snap:
        return jsonify({"error": "Снапшот не найден"}), 404
    update_scene(scene_id, snap["data"], reason="восстановлена")
    return jsonify({"ok": True})
