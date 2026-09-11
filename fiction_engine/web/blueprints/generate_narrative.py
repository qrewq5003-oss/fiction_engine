#!/usr/bin/env python3
"""
История генераций, графики качества и нарративный разбор.

Выделено из generate_bp.py. Блупринт общий — см. generate_prompt.
"""

from flask import render_template, request, jsonify



from .generate_bp import bp
from ..ownership import owned_generation, owned_run, deny
from .helpers import (get_current_project, log_web_error)


@bp.route("/api/generation/<int:gen_id>/delete", methods=["POST"])
def generation_delete(gen_id):
    # DELETE шёл по одному лишь номеру: удалялась чужая генерация.
    if not owned_generation(gen_id):
        return deny("Генерация")
    from engine.db import get_api_key, get_conn
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
    """
    Заметка, которую получит генерация главы chapter_num.

    Парная к /save: один и тот же номер в обоих направлениях. Хранится
    под ключом «после главы chapter_num-1» — перевод делает слой БД.
    """
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
    """
    Сохранить режиссёрскую заметку ДЛЯ главы chapter_num.

    Номер в адресе значит то же, что в GET этого маршрута: «заметка,
    которую получит генерация главы N». Хранится она под ключом
    «после главы N-1» — так устроена таблица, и так её читает
    state_prompts при сборке промпта.

    Перевода здесь не было, и номер уходил в БД как есть. Запись
    попадала на ярус ниже, чем чтение, поэтому пара save(N) → get(N)
    не замыкалась никогда:

        UI сохраняет хвост для главы N   → after_chapter = N
        генерация главы N читает          → after_chapter = N-1

    Заметка молча доставалась СЛЕДУЮЩЕЙ главе. Для «Продолжить главу»
    это вдвойне плохо: инструкции критику и судье («это вторая часть,
    не снижать за отсутствие завязки») до них не доходили, а в промпт
    следующей главы попадало «КОНЕЦ ПЕРВОЙ ЧАСТИ… Продолжай отсюда» —
    указание продолжать предыдущую главу вместо начала новой.

    Найдено прогоном 2026-09-12; в рабочей базе лежала такая заметка
    с 22 марта.
    """
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    if chapter_num < 1:
        return jsonify({"error": "Номер главы начинается с 1"}), 400
    data = request.json or {}
    note = (data.get("note") or "").strip()
    if not note:
        return jsonify({"error": "Пустая заметка"}), 400
    from engine.db import save_director_note
    save_director_note(current["id"], chapter_num - 1, note)
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
    """
    Экспорт контекста проекта для планировщика.

    Параметр ?pid=N выбирает конкретный проект. Раньше он молча
    игнорировался: планировщик запрашивал `/api/project/context?pid=5`,
    а получал активный проект Fiction Engine — то есть импортировал не то,
    что просил, и заметить это было невозможно.
    """
    requested = request.args.get("pid", type=int)
    if requested:
        from engine.db import get_project
        current = get_project(requested)
        if not current:
            return jsonify({"error": f"Проект {requested} не найден"}), 404
    else:
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


@bp.route("/api/inline_call", methods=["POST"])
def inline_call():
    """
    Одиночный вызов модели для внешних инструментов — прежде всего для
    планировщика.

    Смысл в том, чтобы ключи оставались в одном месте. Планировщик раньше
    читал projects.db Fiction Engine напрямую и держал собственные клиенты
    пяти провайдеров; теперь он просто просит FE сделать вызов.

    Тело запроса: {"model": "...", "system": "...", "prompt": "...",
                   "max_tokens": 600}
    Ответ: {"ok": true, "result": "..."}
    """
    data   = request.json or {}
    model  = (data.get("model") or "").strip()
    prompt = (data.get("prompt") or "").strip()
    system = data.get("system") or "Ты помощник писателя. Отвечаешь конкретно."
    try:
        max_tokens = int(data.get("max_tokens") or 600)
    except (TypeError, ValueError):
        return jsonify({"error": "max_tokens должен быть числом"}), 400

    if not model or not prompt:
        return jsonify({"error": "Нужны model и prompt"}), 400

    from engine.db import get_api_key

    provider = model.split("::")[0]
    if not get_api_key(provider):
        return jsonify({"error": f"Нет API ключа для {provider}"}), 400

    try:
        from engine.pipeline import call_llm
        result = call_llm(model, system, prompt, max_tokens=max_tokens)
    except Exception as e:
        log_web_error("inline_call", e)
        return jsonify({"error": str(e)}), 502

    if not result or not result.strip():
        return jsonify({"error": "Модель вернула пустой ответ"}), 502
    return jsonify({"ok": True, "result": result.strip()})


@bp.route("/api/projects/list")
def projects_list_api():
    """Список всех проектов FE для планировщика."""
    from engine.db import get_projects
    projects = get_projects()
    return jsonify({"projects": [
        {"id": p["id"], "name": p["name"], "genre": p.get("genre", "")}
        for p in projects
    ]})
