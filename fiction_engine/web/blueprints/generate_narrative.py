#!/usr/bin/env python3
"""
История генераций, графики качества и нарративный разбор.

Выделено из generate_bp.py. Блупринт общий — см. generate_prompt.
"""

from flask import render_template, request, jsonify



from .generate_bp import bp
from .helpers import (get_current_project, log_web_error)


@bp.route("/api/generation/<int:gen_id>/delete", methods=["POST"])
def generation_delete(gen_id):
    from engine.db import get_conn
    with get_conn() as conn:
        conn.execute("DELETE FROM generation_history WHERE id=?", (gen_id,))
    return jsonify({"ok": True})


@bp.route("/api/generation/clear", methods=["POST"])
def generation_clear():
    """Удалить всю историю генераций текущего проекта."""
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    from engine.db import get_conn
    with get_conn() as conn:
        conn.execute("DELETE FROM generation_history WHERE project_id=?", (current["id"],))
    return jsonify({"ok": True})


@bp.route("/api/generation/tasks/<int:chapter_num>")
def generation_tasks(chapter_num):
    """Последние 5 задач для данного номера главы."""
    current = get_current_project()
    if not current:
        return jsonify({"tasks": []})
    from engine.db import get_conn
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT DISTINCT task FROM generation_history
               WHERE project_id=? AND chapter_num=? AND task IS NOT NULL AND task != ''
               ORDER BY id DESC LIMIT 5""",
            (current["id"], chapter_num)
        ).fetchall()
    return jsonify({"tasks": [r["task"] for r in rows]})


@bp.route("/api/director_note/<int:chapter_num>")
def director_note_get(chapter_num):
    """Режиссёрская заметка для следующей главы (написана после chapter_num-1)."""
    current = get_current_project()
    if not current:
        return jsonify({"note": None})
    from engine.db import get_director_note
    note = get_director_note(current["id"], chapter_num)
    return jsonify({"note": note})


@bp.route("/api/chapter/<int:chapter_num>/text")
def chapter_text_get(chapter_num):
    """Вернуть текст сохранённой главы для склейки."""
    current = get_current_project()
    if not current:
        return jsonify({"text": None})
    from engine.db import get_chapter
    ch = get_chapter(current["id"], chapter_num)
    return jsonify({"text": ch["content"] if ch else None,
                    "words": ch["word_count"] if ch else 0})


@bp.route("/api/director_note/<int:chapter_num>/save", methods=["POST"])
def director_note_save(chapter_num):
    """Сохранить режиссёрскую заметку вручную (например, хвост предыдущей генерации)."""
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    data = request.json or {}
    note = (data.get("note") or "").strip()
    if not note:
        return jsonify({"error": "Пустая заметка"}), 400
    from engine.db import save_director_note
    save_director_note(current["id"], chapter_num, note)
    return jsonify({"ok": True})


@bp.route("/api/quality/graph")
def quality_graph():
    """Данные для графика качества по главам."""
    current = get_current_project()
    if not current:
        return jsonify({"scores": []})
    from engine.db import get_conn
    try:
        with get_conn() as conn:
            rows = conn.execute(
                """SELECT chapter_num, total, details, scored_at
                   FROM chapter_scores WHERE project_id=?
                   ORDER BY chapter_num""",
                (current["id"],)
            ).fetchall()
        import json as _j
        scores = []
        for r in rows:
            d = {}
            try:
                d = _j.loads(r["details"] or "{}")
            except _j.JSONDecodeError:
                # Детали могли быть записаны прежним форматом — показываем
                # оценку без разбора, это не ошибка
                pass
            scores.append({
                "chapter_num": r["chapter_num"],
                "total": r["total"],
                "literary_quality": d.get("literary_quality"),
                "voice_genre":      d.get("voice_genre"),
                "commercial":       d.get("commercial"),
                "scene_health":     d.get("scene_health"),
                "verdict":          d.get("verdict", ""),
                "main_issue":       d.get("main_issue", ""),
                "scored_at":        r["scored_at"],
            })
        return jsonify({"scores": scores})
    except Exception as e:
        return jsonify({"scores": [], "error": str(e)})


@bp.route("/narrative/metrics/<int:chapter_num>")
def narrative_metrics(chapter_num):
    """
    Быстрые метрики без LLM: темп, настроение, конфликт.
    Возвращает JSON. Нет LLM-вызовов, ответ мгновенный.
    """
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет активного проекта"}), 400
    try:
        from engine.narrative_intelligence import get_narrative_metrics
        metrics = get_narrative_metrics(current["id"], chapter_num)
        return jsonify({"ok": True, "metrics": metrics})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/narrative/report/<int:chapter_num>")
def narrative_report(chapter_num):
    """
    Полный нарративный анализ через LLM: арки, промисы, противоречия.
    Может занять 10-20 секунд (2-3 LLM-вызова).
    """
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет активного проекта"}), 400
    try:
        from engine.pipeline import run_narrative_analysis
        from engine.db import get_setting
        project_id  = current["id"]
        model_value = get_setting("model") or ""
        report = run_narrative_analysis(project_id, chapter_num, model_value)
        return jsonify({
            "ok":             report.ok,
            "through_chapter": report.through_chapter,
            "arc_health":     report.arc_health,
            "promise_status": report.promise_status,
            "contradictions": report.contradictions,
            "mood_trajectory":report.mood_trajectory,
            "conflict_density":report.conflict_density,
            "warnings":       report.warnings,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/narrative")
def narrative_page():
    """Страница нарративного анализа серии."""
    current = get_current_project()
    from engine.db import get_chapters
    chapters = get_chapters(current["id"]) if current else []
    return render_template("narrative.html", current=current, chapters=chapters)


@bp.route("/api/project/context")
def project_context():
    """Экспорт контекста проекта для планировщика."""
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    pid = current["id"]

    try:
        from engine.db import get_state
        state = get_state(pid)
    except Exception:
        state = {}

    # Активные обещания из L3
    promises = []
    try:
        from engine.pipeline import get_active_promises_for_project
        promises = get_active_promises_for_project(pid)
    except Exception as e:
        # Именно здесь два битых вызова годами отдавали пустой список
        log_web_error("project/context: не собрать активные обещания", e,
                      project_id=pid)

    return jsonify({
        "project": {
            "id":          pid,
            "name":        current.get("name", ""),
            "genre":       current.get("genre", ""),
            "description": current.get("description", ""),
        },
        "global_state": state.get("global_state", ""),
        "plot_matrix":  state.get("plot_matrix", ""),
        "active_promises": promises,
    })


@bp.route("/api/projects/list")
def projects_list_api():
    """Список всех проектов FE для планировщика."""
    from engine.db import get_projects
    projects = get_projects()
    return jsonify({"projects": [
        {"id": p["id"], "name": p["name"], "genre": p.get("genre", "")}
        for p in projects
    ]})
