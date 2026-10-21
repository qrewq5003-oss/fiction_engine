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
    """Последние 5 задач для данного номера главы — из запусков «Мастерской»
    и из прежней «Генерации»."""
    current = get_current_project()
    if not current:
        return jsonify({"tasks": []})
    from engine.db import get_conn
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT task FROM (
                 SELECT i.input_text AS task, i.created_at AS at FROM pipeline_iterations i
                   JOIN pipeline_runs r ON r.id = i.run_id
                  WHERE r.project_id=? AND r.chapter_num=? AND i.stage='generate'
                 UNION ALL
                 SELECT task, created_at FROM generation_history
                  WHERE project_id=? AND chapter_num=?)
               WHERE task IS NOT NULL AND task != ''
               ORDER BY at DESC""",
            (current["id"], chapter_num, current["id"], chapter_num)
        ).fetchall()
    tasks = list(dict.fromkeys(r["task"] for r in rows))[:5]
    return jsonify({"tasks": tasks})


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


@bp.route("/api/chapter_tone/<int:chapter_num>")
def chapter_tone_get(chapter_num):
    """Тон главы, варианты выбора и второй слой проекта (чтобы не дублировать его)."""
    from engine.genre_mix import chapter_tone_options, project_secondary_key
    current = get_current_project()
    tone = None
    if current:
        from engine.db import get_chapter_tone
        tone = get_chapter_tone(current["id"], chapter_num)
    return jsonify({"tone": tone, "options": chapter_tone_options(),
                    "project_layer": project_secondary_key(current)})


@bp.route("/api/chapter_tone/<int:chapter_num>/save", methods=["POST"])
def chapter_tone_save(chapter_num):
    """Сохранить тон главы chapter_num. Пустое значение — без тона."""
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    from engine.db import set_chapter_tone
    try:
        set_chapter_tone(current["id"], chapter_num, (request.json or {}).get("tone") or None)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True})


@bp.route("/api/chapter/<int:chapter_num>/text")
def chapter_text_get(chapter_num):
    """
    Вернуть текст сохранённой главы — для склейки и для импорта главы в
    планировщик. ?pid=N — глава этого проекта, без него — открытого в FE.
    """
    pid = request.args.get("pid", type=int)
    if pid:
        current, err = _project_from(pid)
        if err:
            return err
    else:
        current = get_current_project()
    if not current:
        return jsonify({"text": None})
    from engine.db import get_chapter
    ch = get_chapter(current["id"], chapter_num)
    return jsonify({"text": ch["content"] if ch else None,
                    "title": (ch.get("title") or "") if ch else "",
                    "words": ch["word_count"] if ch else 0})


@bp.route("/api/chapters/list")
def chapters_list_api():
    """Написанные главы проекта ?pid — планировщику для импорта главы на доску."""
    current, err = _project_from(request.args.get("pid", type=int))
    if err:
        return err
    from engine.db import chapter_writers, get_chapters
    # model — кто писал главу: планировщик разбивает главу той же моделью
    writers = chapter_writers(current["id"])
    return jsonify({"chapters": [{"number": c["number"], "title": c.get("title") or "",
                                  "words": c.get("word_count") or 0,
                                  "model": writers.get(c["number"], "")}
                                 for c in get_chapters(current["id"])]})


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
    if data.get("continue"):
        # «Продолжить главу» — к плану, а не вместо него (db_narrative.add_continuation)
        from engine.db_narrative import add_continuation
        add_continuation(current["id"], chapter_num, note)
        return jsonify({"ok": True})
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
                # Нынешние критерии (0–10) и итог из 50; раньше график ждал
                # прежний формат и рисовал итог 37 по шкале 10 (разбор 21.10)
                **{k: d.get(k) for k in ("voice", "structure", "characters", "scenes", "dialog")},
                "verdict":          d.get("verdict", ""),
                "main_issue":       d.get("main_issue", ""),
                "source":           d.get("source", ""),
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


@bp.route("/narrative/report/<int:chapter_num>", methods=["POST"])
def narrative_report(chapter_num):
    """
    Полный нарративный анализ через LLM: арки, промисы, противоречия.
    Может занять 10-20 секунд (2-3 LLM-вызова).

    Только POST: анализ вызывает модель и пишет расход в api_usage. На GET
    его дёргали бы предзагрузка ссылки, восстановление вкладок и переход
    по истории — каждый раз за деньги. Найдено tools/getcheck.py.
    """
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет активного проекта"}), 400
    try:
        from engine.pipeline import run_narrative_analysis
        from web.blueprints.helpers import pick_model
        project_id  = current["id"]
        model_value = pick_model((request.get_json(silent=True) or {}).get("model", ""))
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


@bp.route("/narrative/purge", methods=["POST"])
def narrative_purge():
    """Убрать из анализа серии главы, которых больше нет."""
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет активного проекта"}), 400
    from engine.db import purge_orphan_chapter_data
    return jsonify({"ok": True, "deleted": purge_orphan_chapter_data(current["id"])})


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
    # chapter — контекст на момент этой главы (ИИ-помощь для сцены гл.5 видела
    # книгу на её конец: L3 гл.22–24 и State последней главы, разбор
    # планировщика 21.10). State героев сцены — POST /api/project/scene_context
    chapter = request.args.get("chapter", type=int)

    try:
        if chapter:
            from engine.db_state import state_for_chapter
            state = state_for_chapter(pid, chapter)
        else:
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

    from engine.db import get_chapters
    chapters = get_chapters(pid)
    last = max((c["number"] for c in chapters), default=0)
    # Что уже случилось — L3 последних написанных глав: AI-помощь
    # планировщика предлагает сцены, не споря с книгой. Только до последней
    # написанной главы: L3 непринятой главы — не история книги
    try:
        from engine.pipeline import get_story_so_far
        story = get_story_so_far(pid, min(last, chapter - 1) if chapter else last)
    except Exception as e:
        log_web_error("project/context: L3", e, project_id=pid)
        story = ""

    return jsonify({
        "project": {
            "id":          pid,
            "name":        current.get("name", ""),
            "genre":       current.get("genre", ""),
            "description": current.get("description", ""),
        },
        # Номер последней написанной главы — планировщик предлагает план следующей
        "last_chapter": last,
        "story_so_far": story,
        "global_state": state.get("global_state", ""),
        "plot_matrix":  state.get("plot_matrix", ""),
        "active_promises": promises,
    })


@bp.route("/api/project/scene_context", methods=["POST"])
def project_scene_context():
    """
    State героев сцены планировщика на момент её главы — для ИИ-помощи: герои
    и детали по тексту сцены, а не обрезка State с начала (у «Фона» главная
    героиня начиналась с 11 650-го знака, разбор планировщика 21.10). POST:
    отбор героев может вызвать модель, а GET обязан быть безопасным.
    """
    data = request.json or {}
    project, err = _project_from(data.get("pid"))
    if err:
        return err
    chapter = int(data.get("chapter") or 0) or None
    focus = str(data.get("focus") or "").strip()
    try:
        if chapter:
            from engine.db_state import state_for_chapter
            state = state_for_chapter(project["id"], chapter)
        else:
            from engine.db import get_state
            state = get_state(project["id"])
        from engine.pipeline_context import extract_relevant_state
        return jsonify({"state_focus": extract_relevant_state(state, focus, before_chapter=chapter)[:8000]
                        if focus else ""})
    except Exception as e:
        log_web_error("project/scene_context", e, project_id=project["id"])
        return jsonify({"error": str(e)[:200]}), 500


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


# ─── Библия серии для планировщика ───────────────────────────────────────────
#
# engine/series_bible.py: места, вещи, события с историей. Планировщик
# показывает их и правит — правка автора тоже новая запись, прошлое не
# перезаписывается. Проект — явный ?pid / "pid": планировщик связан с
# конкретным проектом Fiction Engine, а не с тем, что сейчас открыт.

def _project_from(pid):
    from engine.db import get_project
    if pid:
        p = get_project(int(pid))
        return p, (None if p else (jsonify({"error": f"Проект {pid} не найден"}), 404))
    p = get_current_project()
    return p, (None if p else (jsonify({"error": "Нет проекта"}), 400))


@bp.route("/api/bible")
def bible_get():
    """Текущие факты библии, противоречия и история записей проекта."""
    project, err = _project_from(request.args.get("pid", type=int))
    if err:
        return err
    from engine.series_bible import _rows, conflicts, current
    pid = project["id"]
    return jsonify({"project": {"id": pid, "name": project["name"]},
                    "facts": current(pid), "conflicts": conflicts(pid), "history": _rows(pid)})


@bp.route("/api/bible/set", methods=["POST"])
def bible_set():
    """Запись автора: новый факт или изменение (с причиной). Старое остаётся в истории."""
    data = request.json or {}
    project, err = _project_from(data.get("pid"))
    if err:
        return err
    name, attr, value = (str(data.get(k) or "").strip() for k in ("name", "attr", "value"))
    if not (name and attr and value):
        return jsonify({"error": "нужны name, attr и value"}), 400
    from engine.series_bible import author_set
    author_set(project["id"], str(data.get("kind") or "место"), name, attr, value,
               int(data.get("chapter_num") or 0), str(data.get("reason") or "правка автора"))
    return jsonify({"ok": True})


@bp.route("/api/chapter_plan/<int:chapter_num>/save", methods=["POST"])
def chapter_plan_save(chapter_num):
    """
    План главы из планировщика: записка режиссёра для главы N и факты сцен
    (место, время, кто) — в библию ДО того, как глава написана, чтобы
    генератор получил их блоком «пиши ровно так».
    """
    if chapter_num < 1:
        return jsonify({"error": "Номер главы начинается с 1"}), 400
    data = request.json or {}
    project, err = _project_from(data.get("pid"))
    if err:
        return err
    note = (data.get("note") or "").strip()
    if not note:
        return jsonify({"error": "Пустой план"}), 400
    from engine.db import save_director_note
    from engine.series_bible import PLAN_REASON, author_set
    # Как в director_note_save: заметка для главы N хранится «после главы N-1»
    save_director_note(project["id"], chapter_num - 1, note)
    # Сцены дальше по доске — только сторожу забеганий, писателю никогда
    if "future" in data:
        from engine.run_ahead import save_future
        save_future(project["id"], chapter_num, str(data.get("future") or ""))
    # Новый план главы — вместо прежнего: его записи в библии убрать
    if "facts" in data:
        from engine.series_bible import drop_plan_facts
        drop_plan_facts(project["id"], chapter_num)
    n = 0
    for f in data.get("facts") or []:
        if not isinstance(f, dict):
            continue
        name, attr, value = (str(f.get(k) or "").strip() for k in ("name", "attr", "value"))
        if name and attr and value:
            author_set(project["id"], str(f.get("kind") or "событие"), name, attr, value,
                       chapter_num, PLAN_REASON.format(chapter_num))
            n += 1
    return jsonify({"ok": True, "facts": n})
