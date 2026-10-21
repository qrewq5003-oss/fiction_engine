from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify

bp = Blueprint("main", __name__)


def current_project():
    from engine.db import get_project
    pid = session.get("project_id")
    return get_project(pid) if pid else None


@bp.route("/board")
def board():
    p = current_project()
    if not p:
        return redirect(url_for("main.projects"))
    from engine.db import get_acts, get_scenes, stale_chapter_plans
    acts   = get_acts(p["id"])
    scenes = get_scenes(p["id"])
    stale  = stale_chapter_plans(p["id"]) if p.get("fe_project_id") else []
    # Группируем сцены по act_id
    by_act = {a["id"]: [] for a in acts}
    unassigned = []
    for s in scenes:
        if s["act_id"] and s["act_id"] in by_act:
            by_act[s["act_id"]].append(s)
        else:
            unassigned.append(s)
    # Главы сцен — «Импорт главы» ставит новую главу в акт, где лежит предыдущая
    chapters = [{"act_id": s["act_id"], "chapter_num": s["chapter_num"]} for s in scenes if s["chapter_num"]]
    return render_template("board.html", acts=acts, by_act=by_act, unassigned=unassigned,
                           chapters=chapters, linked=bool(p.get("fe_project_id")), stale=stale)


@bp.route("/map")
def map_view():
    p = current_project()
    if not p:
        return redirect(url_for("main.projects"))
    from engine.db import get_acts, get_scenes, get_links
    acts   = get_acts(p["id"])
    scenes = get_scenes(p["id"])
    links  = get_links(p["id"])
    return render_template("map.html", acts=acts, scenes=scenes, links=links)


@bp.route("/stats")
def stats():
    p = current_project()
    if not p:
        return redirect(url_for("main.projects"))
    from engine.db import get_acts, get_scenes
    acts   = get_acts(p["id"])
    scenes = get_scenes(p["id"])

    # Статистика
    act_map = {a["id"]: a for a in acts}

    by_act = {}
    for a in acts:
        by_act[a["title"]] = {"count": 0, "color": a["color"]}
    by_act["Без акта"] = {"count": 0, "color": "#6b7280"}

    chars_count = {}
    loc_count   = {}
    emo_count   = {}
    incomplete  = []

    for s in scenes:
        # По актам
        act_title = act_map.get(s["act_id"], {}).get("title", "Без акта") if s["act_id"] else "Без акта"
        if act_title not in by_act:
            by_act[act_title] = {"count": 0, "color": "#6b7280"}
        by_act[act_title]["count"] += 1

        # По персонажам
        for c in [x.strip() for x in (s["characters"] or "").split(",") if x.strip()]:
            chars_count[c] = chars_count.get(c, 0) + 1

        # По локациям
        loc = (s["location"] or "").strip()
        if loc:
            loc_count[loc] = loc_count.get(loc, 0) + 1

        # По эмоциям
        emo = (s["emotion"] or "").strip()
        if emo:
            emo_count[emo] = emo_count.get(emo, 0) + 1

        # Незаполненные
        missing = []
        if not s["title"]:        missing.append("название")
        if not s["what_happens"]: missing.append("что происходит")
        if not s["characters"]:   missing.append("персонажи")
        if not s["location"]:     missing.append("локация")
        if missing:
            incomplete.append({"id": s["id"], "title": s["title"] or f"Сцена #{s['id']}", "missing": missing})

    # Время в плане: сцены в порядке доски — акты по номеру, без акта в конце
    from engine.timeline import check as check_timeline
    order = {a["id"]: i for i, a in enumerate(acts)}
    in_plan = sorted(scenes, key=lambda s: (order.get(s["act_id"], len(order)), s["position"] or 0))

    return render_template("stats.html",
        scenes=scenes, by_act=by_act, timeline=check_timeline(in_plan),
        chars_count=sorted(chars_count.items(), key=lambda x: -x[1]),
        loc_count=sorted(loc_count.items(), key=lambda x: -x[1]),
        emo_count=sorted(emo_count.items(), key=lambda x: -x[1]),
        incomplete=incomplete
    )


@bp.route("/export")
def export():
    p = current_project()
    if not p:
        return redirect(url_for("main.projects"))
    from engine.db import get_acts, get_scenes
    acts   = get_acts(p["id"])
    scenes = get_scenes(p["id"])
    act_map = {a["id"]: a for a in acts}
    for s in scenes:
        s["act_title"] = act_map.get(s["act_id"], {}).get("title", "") if s["act_id"] else ""
    loose = [s for s in scenes if s["act_id"] not in act_map]
    nxt, why = _next_chapter(p)
    return render_template("export.html", acts=acts, scenes=scenes, loose=loose,
                           next_chapter=nxt, next_warning=why)


def _next_chapter(project: dict) -> tuple[int | None, str]:
    """
    → (глава после последней написанной в связанной книге FE, предупреждение).
    FE не ответил — (None, причина): раньше молча 1, и «Отправить» перезаписывал
    план главы 1 (разбор планировщика 21.10). Список глав — лёгкий запрос, а не
    контекст с L3 и обещаниями, который не успевал за 2 с.
    """
    if not project.get("fe_project_id"):
        return 1, ""
    import json
    from .api_bp import _fe_error, _fe_get
    try:
        with _fe_get(f"/api/chapters/list?pid={project['fe_project_id']}", timeout=5) as r:
            chapters = json.loads(r.read()).get("chapters") or []
        return max((int(c.get("number") or 0) for c in chapters), default=0) + 1, ""
    except Exception as e:
        return None, f"{_fe_error(e)} — номер главы не подставлен, укажи его сам"


@bp.route("/bible")
def bible():
    p = current_project()
    if not p:
        return redirect(url_for("main.projects"))
    return render_template("bible.html", linked=bool(p.get("fe_project_id")))


@bp.route("/projects")
def projects():
    from engine.db import get_projects
    return render_template("projects.html", projects=get_projects())


@bp.route("/projects/new", methods=["POST"])
def project_new():
    data = request.json or {}
    from engine.db import create_project
    pid = create_project(data.get("name","Новый проект"), data.get("genre",""), data.get("description",""))
    session["project_id"] = pid
    return jsonify({"ok": True, "id": pid})


@bp.route("/projects/<int:pid>/delete", methods=["POST"])
def project_delete(pid):
    from engine.db import delete_project
    delete_project(pid)
    # Сбрасывать открытый проект — только если удалён он (разбор 21.10)
    if session.get("project_id") == pid:
        session.pop("project_id", None)
    return jsonify({"ok": True})
