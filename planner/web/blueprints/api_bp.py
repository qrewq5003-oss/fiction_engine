from flask import Blueprint, session, request, jsonify

bp = Blueprint("api", __name__, url_prefix="/api")


def current_pid():
    return session.get("project_id")


# ─── Scenes ───────────────────────────────────────────────────────────────────

@bp.route("/scenes")
def scenes_list():
    pid = current_pid()
    if not pid: return jsonify({"scenes": []})
    from engine.db import get_scenes
    return jsonify({"scenes": get_scenes(pid)})


@bp.route("/scenes/new", methods=["POST"])
def scene_new():
    pid = current_pid()
    if not pid: return jsonify({"error": "Нет проекта"}), 400
    data   = request.json or {}
    act_id = data.get("act_id")
    from engine.db import create_scene
    sid = create_scene(pid, act_id)
    return jsonify({"ok": True, "id": sid})


@bp.route("/scenes/move", methods=["POST"])
def scene_move():
    data = request.json or {}
    sid      = data.get("scene_id")
    act_id   = data.get("act_id")
    position = data.get("position", 0)
    if not sid: return jsonify({"error": "Нет scene_id"}), 400
    from engine.db import move_scene
    move_scene(sid, act_id, position)
    return jsonify({"ok": True})


@bp.route("/scenes/reorder", methods=["POST"])
def scene_reorder():
    """Пересохранить позиции сцен в акте после drag & drop."""
    data   = request.json or {}
    order  = data.get("order", [])  # [{scene_id, position}]
    act_id = data.get("act_id")
    from engine.db import get_conn
    with get_conn() as conn:
        for item in order:
            conn.execute(
                "UPDATE scenes SET act_id=?, position=? WHERE id=?",
                (act_id, item["position"], item["scene_id"])
            )
    return jsonify({"ok": True})


# ─── Acts ─────────────────────────────────────────────────────────────────────

@bp.route("/acts")
def acts_list():
    pid = current_pid()
    if not pid: return jsonify({"acts": []})
    from engine.db import get_acts
    return jsonify({"acts": get_acts(pid)})


@bp.route("/acts/save", methods=["POST"])
def act_save():
    pid = current_pid()
    if not pid: return jsonify({"error": "Нет проекта"}), 400
    data  = request.json or {}
    from engine.db import save_act
    aid = save_act(pid, data.get("id"), data.get("number", 1),
                   data.get("title", "Акт"), data.get("color", "#6b7280"))
    return jsonify({"ok": True, "id": aid})


@bp.route("/acts/<int:act_id>/delete", methods=["POST"])
def act_delete(act_id):
    from engine.db import delete_act
    delete_act(act_id)
    return jsonify({"ok": True})


# ─── Links ───────────────────────────────────────────────────────────────────

@bp.route("/links")
def links_list():
    pid = current_pid()
    if not pid: return jsonify({"links": []})
    from engine.db import get_links
    return jsonify({"links": get_links(pid)})


@bp.route("/links/save", methods=["POST"])
def link_save():
    data = request.json or {}
    from engine.db import save_link
    lid = save_link(data["from_id"], data["to_id"],
                    data.get("link_type", "cause"), data.get("label", ""))
    return jsonify({"ok": True, "id": lid})


@bp.route("/links/<int:link_id>/delete", methods=["POST"])
def link_delete(link_id):
    from engine.db import delete_link
    delete_link(link_id)
    return jsonify({"ok": True})


# ─── AI Assistant ─────────────────────────────────────────────────────────────

@bp.route("/ai/assist", methods=["POST"])
def ai_assist():
    data   = request.json or {}
    action = data.get("action", "develop")
    scene  = data.get("scene", {})
    model  = data.get("model", "")

    ACTIONS = {
        "develop":  "Развей идею этой сцены — что можно добавить, углубить, сделать интереснее.",
        "conflict": "Предложи конфликт или напряжение для этой сцены. Что может пойти не так?",
        "subtext":  "Что персонажи не говорят вслух? Добавь подтекст — скрытые мотивы, недосказанность.",
        "next":     "Что логично происходит после этой сцены? Предложи 2-3 варианта следующей сцены.",
        "rewrite":  "Перепиши описание этой сцены — более конкретно, с деталями.",
    }

    instruction = ACTIONS.get(action, ACTIONS["develop"])
    scene_text  = (
        f"Сцена: {scene.get('title','')}\n"
        f"Локация: {scene.get('location','')} / {scene.get('time_of_day','')}\n"
        f"Персонажи: {scene.get('characters','')}\n"
        f"Что происходит: {scene.get('what_happens','')}\n"
        f"Эмоция: {scene.get('emotion','')}\n"
        f"Заметки: {scene.get('notes','')}"
    )

    # Вызов модели делает Fiction Engine: ключи живут там
    try:
        import requests as req
        resp = req.post(f"{_fe_base_url()}/api/inline_call", json={
            "model": model,
            "system": "Ты помощник сценариста и писателя. Отвечаешь конкретно и по делу.",
            "prompt": f"{instruction}\n\n{scene_text}",
            "max_tokens": 600
        }, timeout=60)
        if resp.ok:
            return jsonify({"ok": True, "result": resp.json().get("result", "")})
    except Exception:
        pass

    return jsonify({
        "error": f"Fiction Engine недоступен ({_fe_base_url()}). "
                 "Запусти его или задай FE_URL."
    }), 503


# ─── Export to Fiction Engine ─────────────────────────────────────────────────

@bp.route("/export/send", methods=["POST"])
def export_send():
    data       = request.json or {}
    scene_ids  = data.get("scene_ids", [])
    chapter_num = data.get("chapter_num", 1)

    from engine.db import get_scene
    scenes = [get_scene(sid) for sid in scene_ids if get_scene(sid)]

    # Строим промт
    lines = [f"ПЛАН ГЛАВЫ {chapter_num}\n"]
    for i, s in enumerate(scenes, 1):
        lines.append(f"СЦЕНА {i}: {s['title'] or 'Без названия'}")
        if s["location"]:    lines.append(f"  Локация: {s['location']} / {s['time_of_day']}")
        if s["characters"]:  lines.append(f"  Персонажи: {s['characters']}")
        if s["what_happens"]:lines.append(f"  Что происходит: {s['what_happens']}")
        if s["emotion"]:     lines.append(f"  Эмоция: {s['emotion']}")
        lines.append("")

    prompt_text = "\n".join(lines)

    # Отправляем в FE как режиссёрскую заметку к главе.
    # Путь именно такой: /api/director_note/<N>/save. Прежний вариант бил
    # в /api/director_note без номера главы — такого маршрута в FE нет,
    # запрос всегда падал, а ответ приходил с sent: false, будто FE просто
    # не запущен.
    try:
        import requests as req
        resp = req.post(f"{_fe_base_url()}/api/director_note/{chapter_num}/save",
                        json={"note": prompt_text}, timeout=10)
        if resp.ok:
            return jsonify({"ok": True, "prompt": prompt_text, "sent": True})
    except Exception:
        pass

    # FE недоступен — возвращаем промт для ручного копирования
    return jsonify({"ok": True, "prompt": prompt_text, "sent": False})


# ─── Статус системы ───────────────────────────────────────────────────────────

@bp.route("/status")
def system_status():
    """
    Состояние связки планировщик ↔ Fiction Engine.

    Ключи спрашиваются у FE по HTTP, а не читаются из его projects.db.
    Прежний вариант лез в чужую базу напрямую: планировщик знал её путь,
    схему таблицы api_keys и держал собственных клиентов пяти провайдеров.
    Любое изменение в FE ломало бы планировщик молча.
    """
    import json as _json
    import urllib.request

    fe_server, keys = False, {}
    try:
        with urllib.request.urlopen(f"{_fe_base_url()}/api/keys/status", timeout=2) as r:
            raw = _json.loads(r.read())
        fe_server = True
        # FE отдаёт {провайдер: маскированный ключ}; нам нужен сам факт наличия
        keys = {
            "anthropic": "anthropic_direct" in raw,
            "openai":    "openai_direct" in raw,
            "gemini":    "gemini_direct" in raw,
            "deepseek":  "deepseek_direct" in raw,
            "nano":      "nano_gpt" in raw,
        }
    except Exception:
        # FE не запущен — это штатное состояние, а не ошибка:
        # планировщиком можно пользоваться и без него
        pass

    return jsonify({
        "fe_server": fe_server,
        "keys":      keys,
        "has_keys":  any(keys.values()),
    })


@bp.route("/fe/projects")
def fe_projects():
    """Список проектов FE."""
    try:
        import urllib.request, json as _json
        with urllib.request.urlopen(f"{_fe_base_url()}/api/projects/list", timeout=3) as r:
            return jsonify(_json.loads(r.read()))
    except Exception as e:
        return jsonify({"error": str(e), "projects": []})


@bp.route("/fe/import/<int:fe_pid>", methods=["POST"])
def fe_import(fe_pid):
    """Импортировать контекст проекта из FE в планировщик."""
    pid = current_pid()
    if not pid:
        return jsonify({"error": "Нет проекта в планировщике"}), 400

    try:
        import urllib.request, json as _json
        with urllib.request.urlopen(
            f"{_fe_base_url()}/api/project/context?pid={fe_pid}", timeout=10
        ) as r:
            data = _json.loads(r.read())
    except Exception as e:
        return jsonify({"error": f"FE недоступен: {e}"}), 503

    # Обновляем описание проекта в планировщике
    # save_logline здесь не нужен — и его в engine.db нет: импорт
    # валил весь обработчик с ImportError, то есть импорт из FE
    # не работал вовсе
    from engine.db import update_project, get_project
    project = get_project(pid)
    if not project:
        return jsonify({"error": "Проект не найден"}), 404

    fe_proj = data.get("project", {})
    global_state = data.get("global_state", "")
    plot_matrix  = data.get("plot_matrix", "")
    promises     = data.get("active_promises", [])

    # Собираем описание из state engine
    context_parts = []
    if global_state:
        context_parts.append(f"СОСТОЯНИЕ МИРА:\n{global_state[:800]}")
    if plot_matrix:
        context_parts.append(f"АКТИВНЫЕ ЛИНИИ:\n{plot_matrix[:600]}")
    if promises:
        context_parts.append("НЕЗАКРЫТЫЕ ОБЕЩАНИЯ:\n" + "\n".join(f"- {p}" for p in promises[:10]))

    description = "\n\n".join(context_parts) if context_parts else project.get("description", "")

    update_project(pid,
        name=project["name"],
        genre=fe_proj.get("genre") or project.get("genre", ""),
        description=description
    )

    return jsonify({
        "ok": True,
        "imported": {
            "genre":    fe_proj.get("genre", ""),
            "promises": len(promises),
            "has_state": bool(global_state),
        }
    })
