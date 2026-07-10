from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify

bp = Blueprint("scene", __name__)


def current_project():
    from engine.db import get_project
    pid = session.get("project_id")
    return get_project(pid) if pid else None


@bp.route("/scene/<int:scene_id>")
def scene_detail(scene_id):
    from engine.db import get_scene, get_acts, get_snapshots
    s = get_scene(scene_id)
    if not s:
        return redirect(url_for("main.board"))
    p = current_project()
    acts      = get_acts(p["id"]) if p else []
    snapshots = get_snapshots(scene_id)
    return render_template("scene.html", scene=s, acts=acts, snapshots=snapshots)


@bp.route("/scene/<int:scene_id>/save", methods=["POST"])
def scene_save(scene_id):
    from engine.db import update_scene
    data = request.json or {}
    update_scene(scene_id, data, reason="изменена")
    return jsonify({"ok": True})


@bp.route("/scene/<int:scene_id>/delete", methods=["POST"])
def scene_delete(scene_id):
    from engine.db import delete_scene
    delete_scene(scene_id)
    return jsonify({"ok": True})


@bp.route("/scene/<int:scene_id>/snapshot/<int:snap_id>/restore", methods=["POST"])
def snapshot_restore(scene_id, snap_id):
    from engine.db import get_snapshots, update_scene
    snaps = get_snapshots(scene_id)
    snap  = next((s for s in snaps if s["id"] == snap_id), None)
    if not snap:
        return jsonify({"error": "Снапшот не найден"}), 404
    update_scene(scene_id, snap["data"], reason="восстановлена")
    return jsonify({"ok": True})
