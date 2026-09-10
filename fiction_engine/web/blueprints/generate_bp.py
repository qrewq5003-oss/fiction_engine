"""Blueprint: генерация, pipeline, prep, prompt, edit, validate."""
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from engine.db import (get_chapter, get_chapters, save_chapter, get_api_key,
                       get_prep, save_prep, PREP_SECTIONS,
                       get_generation_history, get_generation_by_id,
                       save_author_edit, get_pipeline_run, get_pipeline_iterations)
from engine.api import get_all_models_flat
from engine.state import build_prompt   # используется в /prompt/generate
from engine.pipeline import score_text  # публичный API скоринга
from .helpers import get_current_project, after_chapter_saved

bp = Blueprint("generate", __name__)



# ─── Фоновая генерация ────────────────────────────────────────────────────────
import threading, uuid

_jobs: dict[str, dict] = {}   # job_id -> dict
_jobs_lock = threading.Lock()


def _make_job(job_id: str):
    return {"status": "running", "result": None, "error": None, "warning": None,
            "gen_id": None, "truncated": False, "cut_reason": "", "word_count": 0}


def _classify_api_error(err: str) -> str:
    """Преобразовать техническое сообщение об ошибке в читаемое."""
    err_l = err.lower()
    if "rate_limit" in err_l or "429" in err_l:
        return "Превышен лимит запросов. Подожди минуту."
    if "context_length" in err_l:
        return "Контекст слишком большой. Уменьши Подготовку."
    if "invalid_api_key" in err_l or "authentication" in err_l:
        return "Неверный API ключ."
    if "timeout" in err_l:
        return "Timeout — попробуй снова."
    return f"Ошибка: {err}"


def _set_job(job_id, **kwargs):
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


def _cleanup_old_jobs():
    """Держим не больше 50 последних задач в памяти."""
    with _jobs_lock:
        if len(_jobs) > 50:
            oldest = list(_jobs.keys())[:-50]
            for k in oldest:
                del _jobs[k]

# ─── Генерация ────────────────────────────────────────────────────────────────

@bp.route("/generate")
def generate_page():
    current = get_current_project()
    if not current:
        flash("Сначала выбери проект", "error")
        return redirect(url_for("main.index"))
    models = get_all_models_flat()
    chapters = get_chapters(current["id"])
    return render_template("generate.html", current=current, models=models, chapters=chapters)


@bp.route("/generate/run", methods=["POST"])
def generate_run():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    data = request.json or {}
    chapter_num = data.get("chapter_num")
    mode        = data.get("mode", "quick")
    model_value = data.get("model")
    task        = data.get("task", "").strip()
    if not all([chapter_num, model_value, task]):
        return jsonify({"error": "Нужны chapter_num, model и task"}), 400
    provider = model_value.split("::")[0]
    if not get_api_key(provider):
        return jsonify({"error": f"Нет API ключа для {provider}. Добавь в Настройках."}), 400

    # Создаём задачу и запускаем в фоне
    _cleanup_old_jobs()
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = _make_job(job_id)

    project_snapshot = dict(current)  # копия чтобы не держать контекст запроса

    def _worker():
        try:
            from engine.pipeline import run_generation
            result = run_generation(project_snapshot, chapter_num, mode, model_value, task)
            gen_id = _save_gen_history(project_snapshot["id"], chapter_num,
                                       model_value, mode, task, result["text"])
            _set_job(job_id, status="done", result=result["text"],
                     gen_id=gen_id, warning=result["warning"],
                     truncated=result.get("truncated", False),
                     cut_reason=result.get("cut_reason", ""),
                     word_count=result.get("word_count", 0))

        except Exception as e:
            _set_job(job_id, status="error", error=_classify_api_error(str(e)))

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return jsonify({"ok": True, "job_id": job_id})


@bp.route("/generate/status/<job_id>")
def generate_status(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    return jsonify({
        "status":     job["status"],
        "result":     job["result"],
        "error":      job["error"],
        "warning":    job["warning"],
        "gen_id":     job["gen_id"],
        # Флаг для интерфейса: глава не дописана — предложить продолжение
        # одной кнопкой, вместо того чтобы автор сам заметил обрыв.
        "truncated":  job.get("truncated", False),
        "cut_reason": job.get("cut_reason", ""),
        "word_count": job.get("word_count", 0),
    })


def _save_gen_history(project_id, chapter_num, model, mode, task, text):
    from engine.db import get_conn, init_generation_history
    try:
        init_generation_history()
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO generation_history (project_id,chapter_num,model,mode,task,result_text,word_count) VALUES (?,?,?,?,?,?,?)",
                (project_id, chapter_num, model, mode, task, text, len(text.split()))
            )
            return cur.lastrowid
    except Exception:
        return None


@bp.route("/generate/save", methods=["POST"])
def generate_save():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    data = request.json or {}
    chapter_num = data.get("chapter_num")
    text        = data.get("text", "").strip()
    model_value = data.get("model", "")
    if not chapter_num or not text:
        return jsonify({"error": "Нужны chapter_num и text"}), 400
    save_chapter(current["id"], chapter_num, text, f"Глава {chapter_num}")
    result = {"ok": True}
    if model_value:
        result.update(after_chapter_saved(current["id"], chapter_num, text, model_value))
    return jsonify(result)


@bp.route("/generate/validate", methods=["POST"])
def generate_validate():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    data = request.json or {}
    chapter_num = data.get("chapter_num")
    task        = data.get("task", "").strip()
    model_value = data.get("model")
    if not task or not chapter_num:
        return jsonify({"error": "Нужны task и chapter_num"}), 400
    try:
        from engine.prevalidation import prevalidate_chapter
        return jsonify(prevalidate_chapter(current["id"], chapter_num, task, model_value))
    except Exception as e:
        return jsonify({"ok": True, "blocking": [], "warnings": [], "error": str(e)})


# ─── История генераций ────────────────────────────────────────────────────────

@bp.route("/api/generation/history")
def generation_history():
    current = get_current_project()
    if not current:
        return jsonify([])
    return jsonify(get_generation_history(current["id"]))


@bp.route("/api/generation/<int:gen_id>")
def generation_detail(gen_id):
    gen = get_generation_by_id(gen_id)
    if not gen:
        return jsonify({"error": "Не найдено"}), 404
    return jsonify(gen)


@bp.route("/api/generation/<int:gen_id>/score", methods=["POST"])
def generation_score(gen_id):
    from engine.db import get_generation_by_id, save_generation_score, get_conn
    rec = get_generation_by_id(gen_id)
    if not rec:
        return jsonify({"error": "Запись не найдена"}), 404
    text = rec.get("result_text", "")
    if not text or len(text.strip()) < 50:
        return jsonify({"error": "Текст слишком короткий"}), 400
    scorer_model = rec.get("model", "")
    try:
        with get_conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key='scorer_model'").fetchone()
        if row and row["value"]:
            scorer_model = row["value"]
    except Exception:
        pass
    current = get_current_project()
    genre = current.get("genre", "") if current else ""
    provider = scorer_model.split("::")[0] if "::" in scorer_model else ""
    if not get_api_key(provider):
        return jsonify({"error": f"Нет API ключа для {provider}"}), 400
    try:
        details = score_text(text, genre, scorer_model)
        save_generation_score(gen_id, details["total"], details)
        return jsonify({"ok": True, "score": details})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Prompt / Prep / Edit ────────────────────────────────────────────────────

@bp.route("/prompt")
def prompt_page():
    current = get_current_project()
    if not current:
        flash("Сначала выбери проект", "error")
        return redirect(url_for("main.index"))
    models = get_all_models_flat()
    chapters = get_chapters(current["id"])
    return render_template("prompt.html", current=current, models=models, chapters=chapters)


@bp.route("/prompt/generate", methods=["POST"])
def prompt_generate():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    chapter_num = request.json.get("chapter_num")
    mode = request.json.get("mode", "quick")
    if not chapter_num:
        return jsonify({"error": "Нужен номер главы"}), 400
    try:
        prompt = build_prompt(current["id"], chapter_num, mode, current)
        return jsonify({"ok": True, "prompt": prompt})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/prep")
def prep_page():
    current = get_current_project()
    if not current:
        flash("Сначала выбери проект", "error")
        return redirect(url_for("main.index"))
    prep = get_prep(current["id"])
    return render_template("prep.html", current=current, prep=prep, sections=PREP_SECTIONS)


@bp.route("/prep/save", methods=["POST"])
def prep_save():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    section = request.json.get("section", "").strip()
    content = request.json.get("content", "")
    if section not in PREP_SECTIONS:
        return jsonify({"error": "Неизвестная секция"}), 400
    save_prep(current["id"], section, content)
    return jsonify({"ok": True})


@bp.route("/api/prep/size")
def prep_size():
    current = get_current_project()
    if not current:
        return jsonify({"chars": 0})
    from engine.db import get_prep_context
    chars = len(get_prep_context(current["id"]))
    return jsonify({"chars": chars, "warning": chars > 8000,
                    "message": f"{chars} символов" + (" — возможно превышение" if chars > 8000 else "")})


@bp.route("/edit")
def edit_page():
    current = get_current_project()
    if not current:
        flash("Сначала выбери проект", "error")
        return redirect(url_for("main.index"))
    models = get_all_models_flat()
    chapters = get_chapters(current["id"])
    from engine.scene_editor import EDIT_MODES
    return render_template("edit.html", current=current, models=models,
                           chapters=chapters, edit_modes=EDIT_MODES)


@bp.route("/edit/run", methods=["POST"])
def edit_run():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    data = request.json or {}
    text        = data.get("text", "").strip()
    mode        = data.get("mode", "cliches")
    model_value = data.get("model")
    custom      = data.get("custom", "").strip()
    if not text or not model_value:
        return jsonify({"error": "Нужны text и model"}), 400
    if not get_api_key(model_value.split("::")[0]):
        return jsonify({"error": "Нет API ключа"}), 400
    try:
        from engine.scene_editor import edit_scene
        result = edit_scene(current["id"], text, mode, model_value, custom)
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500




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
            try: d = _j.loads(r["details"] or "{}")
            except Exception: pass
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

# ─── Pipeline ────────────────────────────────────────────────────────────────

@bp.route("/pipeline")
def pipeline_page():
    current = get_current_project()
    if not current:
        flash("Сначала выбери проект", "error")
        return redirect(url_for("main.index"))
    from engine.db import get_pipeline_runs, init_pipeline_tables
    init_pipeline_tables()
    runs = get_pipeline_runs(current["id"])
    chapters = get_chapters(current["id"])
    models = get_all_models_flat()
    return render_template("pipeline.html", current=current, runs=runs,
                           chapters=chapters, models=models)


@bp.route("/pipeline/start", methods=["POST"])
def pipeline_start():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    data = request.json or {}
    required = ["chapter_num","generation_prompt","model_gen","model_critic","model_editor","model_judge"]
    if not all(data.get(k) for k in required):
        return jsonify({"error": "Заполни все поля"}), 400
    try:
        from engine.pipeline import start_pipeline
        prefill = data.get("prefill", "")
        result = start_pipeline(project_id=current["id"], prefill=prefill,
                                **{k: data[k] for k in required})
        # start_pipeline кладёт truncated/cut_reason в results на шаге generate
        return jsonify({"ok": True, **result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/pipeline/continue", methods=["POST"])
def pipeline_continue():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    data = request.json or {}
    if not data.get("run_id"):
        return jsonify({"error": "Нет run_id"}), 400
    try:
        from engine.pipeline import continue_pipeline
        result = continue_pipeline(run_id=data["run_id"], project_id=current["id"],
                                    chapter_num=data.get("chapter_num"),
                                    generation_prompt=data.get("generation_prompt",""),
                                    previous_text=data.get("previous_text",""),
                                    previous_critique=data.get("previous_critique",""))
        return jsonify({"ok": True, **result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _try_state_update_after_accept(project_id: int, chapter_num: int,
                                    model_value: str) -> bool:
    """
    Запустить анализ главы и применить изменения к State Engine.
    Возвращает True если State успешно обновлён. Никогда не бросает исключений.
    """
    provider = model_value.split("::")[0] if "::" in model_value else model_value
    if not get_api_key(provider):
        return False
    try:
        from engine.state import analyze_chapter
        from engine.db import (mark_update_applied, get_pending_updates,
                               merge_analysis_into_state)
        result   = analyze_chapter(project_id, chapter_num, model_value)
        auto_id  = result.get("update_id")
        if not auto_id:
            return False
        # Применяем через тот же merge, что и ручной путь /state/apply.
        # Раньше здесь читались ключи new_global_state / new_plot_matrix,
        # которых нет в таблице state_updates: они всегда были None, State
        # переписывался сам в себя, а update помечался применённым —
        # то есть анализ молча терялся.
        for u in get_pending_updates(project_id):
            if u["id"] == auto_id:
                raw = u.get("raw_analysis")
                if not raw:
                    return False
                res = merge_analysis_into_state(
                    project_id, raw, u.get("chapter_num", chapter_num)
                )
                mark_update_applied(auto_id)
                return bool(res.get("changed"))
    except Exception as e:
        _log_state_update_failure(project_id, chapter_num, e)
    return False


def _log_state_update_failure(project_id: int, chapter_num: int, exc: Exception) -> None:
    """Автообновление State — некритично, но должно быть видно в логах."""
    try:
        from engine.logger import get_logger
        get_logger(__name__).error(
            "auto state update failed", exc,
            project_id=project_id, chapter_num=chapter_num,
        )
    except Exception:
        pass


@bp.route("/pipeline/accept", methods=["POST"])
def pipeline_accept():
    data        = request.json or {}
    run_id      = data.get("run_id")
    chapter_num = data.get("chapter_num")
    final_text  = data.get("final_text", "")
    model_value = data.get("model_value")
    if not run_id:
        return jsonify({"error": "Нет run_id"}), 400

    from engine.pipeline import accept_pipeline
    accept_pipeline(run_id)

    current       = get_current_project()
    state_updated = False
    if current and chapter_num and final_text:
        save_chapter(current["id"], chapter_num, final_text, f"Глава {chapter_num} (pipeline)")
        if model_value:
            state_updated = _try_state_update_after_accept(current["id"], chapter_num, model_value)

        # ── Записываем правку автора для DATA_DRIVEN_LEARNING ──────────────
        # Находим оригинальный текст (последняя итерация generate/edit)
        # и judge_score из последнего вердикта.
        try:
            iters      = get_pipeline_iterations(run_id)
            gen_iter   = next((i for i in reversed(iters) if i["stage"] in ("generate", "edit")), None)
            judge_iter = next((i for i in reversed(iters) if i["stage"] == "judge"), None)
            orig_text  = gen_iter["output_text"] if gen_iter else ""
            j_score    = judge_iter["score"] if judge_iter else None
            # Если final_text отличается от оригинала — автор редактировал вручную
            action = "manual_edit" if orig_text and final_text != orig_text else "accept"
            save_author_edit(
                project_id=current["id"],
                chapter_num=int(chapter_num),
                run_id=int(run_id),
                original_text=orig_text or "",
                accepted_text=final_text,
                action=action,
                judge_score=j_score,
            )
        except Exception:
            pass  # Некритично — не ломаем accept

    return jsonify({"ok": True, "state_updated": state_updated})


@bp.route("/pipeline/reject", methods=["POST"])
def pipeline_reject():
    run_id = (request.json or {}).get("run_id")
    if not run_id:
        return jsonify({"error": "Нет run_id"}), 400
    from engine.pipeline import reject_pipeline
    reject_pipeline(run_id)

    # ── Записываем отклонение для DATA_DRIVEN_LEARNING ─────────────────────
    current = get_current_project()
    if current:
        try:
            data_r     = request.json or {}
            iters      = get_pipeline_iterations(run_id)
            gen_iter   = next((i for i in reversed(iters) if i["stage"] in ("generate", "edit")), None)
            judge_iter = next((i for i in reversed(iters) if i["stage"] == "judge"), None)
            orig_text  = gen_iter["output_text"] if gen_iter else ""
            j_score    = judge_iter["score"] if judge_iter else None
            reason     = data_r.get("rejection_reason", "")
            ch_num     = data_r.get("chapter_num") or (judge_iter or {}).get("chapter_num")
            if orig_text and ch_num:
                save_author_edit(
                    project_id=current["id"],
                    chapter_num=int(ch_num),
                    run_id=int(run_id),
                    original_text=orig_text,
                    accepted_text="",  # отклонено — нет принятого текста
                    action="reject",
                    rejection_reason=reason,
                    judge_score=j_score,
                )
        except Exception:
            pass

    return jsonify({"ok": True})



@bp.route("/pipeline/delete-history", methods=["POST"])
def pipeline_delete_history():
    """Удалить всю историю pipeline запусков проекта."""
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    from engine.db_core import get_conn
    with get_conn() as conn:
        # Сначала удаляем итерации (дочерние записи)
        conn.execute(
            "DELETE FROM pipeline_iterations WHERE run_id IN "
            "(SELECT id FROM pipeline_runs WHERE project_id=?)",
            (current["id"],)
        )
        # Потом сами запуски
        conn.execute(
            "DELETE FROM pipeline_runs WHERE project_id=?",
            (current["id"],)
        )
        deleted = conn.execute("SELECT changes()").fetchone()[0]
    return jsonify({"ok": True, "deleted": deleted})

@bp.route("/pipeline/cleanup", methods=["POST"])
def pipeline_cleanup():
    """Сбросить все зависшие запуски (статус running → rejected)."""
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    from engine.db_core import get_conn
    with get_conn() as conn:
        conn.execute(
            "UPDATE pipeline_runs SET status='rejected', finished_at=datetime('now') "
            "WHERE project_id=? AND status='running'",
            (current["id"],)
        )
        affected = conn.execute("SELECT changes()").fetchone()[0]
    return jsonify({"ok": True, "cleaned": affected})


@bp.route("/pipeline/<int:run_id>/history")
def pipeline_history(run_id):
    from engine.db import get_pipeline_run, get_pipeline_iterations
    run = get_pipeline_run(run_id)
    if not run:
        return jsonify({"error": "Не найден"}), 404
    iters = get_pipeline_iterations(run_id)
    return jsonify({"run": dict(run), "iterations": iters})


@bp.route("/pipeline/<int:run_id>/compare")
def pipeline_compare(run_id):
    current = get_current_project()
    from engine.db import get_pipeline_run, get_pipeline_iterations
    run = get_pipeline_run(run_id)
    if not run:
        flash("Запуск не найден", "error")
        return redirect(url_for("generate.pipeline_page"))
    iters = get_pipeline_iterations(run_id)
    by_iter = {}
    for it in iters:
        n = it["iteration"]
        if n not in by_iter:
            by_iter[n] = {}
        by_iter[n][it["stage"]] = it
    return render_template("pipeline_compare.html", current=current, run=run, by_iter=by_iter)


# ─── Narrative Intelligence ───────────────────────────────────────────────────

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


@bp.route("/api/prompt-assist", methods=["POST"])
def prompt_assist():
    """Ассистент промта: собирает контекст и генерирует черновик промта для главы."""
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет активного проекта"}), 400

    data = request.json or {}
    chapter_num = data.get("chapter_num")
    if not chapter_num:
        return jsonify({"error": "Укажи номер главы"}), 400

    project_id = current["id"]

    try:
        from engine.db import get_l3_summary, get_l3_summaries, get_api_key
        from engine.db_settings import get_prep, get_prep_context
        from engine.db_state import get_state

        # 1. Plan for this chapter from plot section
        prep = get_prep(project_id)
        plot_text = prep.get("plot", "").strip()

        # 2. L3 summary of previous chapter
        prev_l3 = get_l3_summary(project_id, chapter_num - 1) if chapter_num > 1 else None
        prev_l3_text = ""
        if prev_l3:
            prev_l3_text = (
                f"СОБЫТИЯ гл.{chapter_num-1}: {prev_l3.get('events', '')}\n"
                f"ПЕРСОНАЖИ: {prev_l3.get('characters', '')}\n"
                f"КОНФЛИКТЫ: {prev_l3.get('conflicts', '')}\n"
                f"НАСТРОЕНИЕ: {prev_l3.get('mood', '')}\n"
                f"НЕЗАКРЫТЫЕ ЛИНИИ: {prev_l3.get('promises', '')}"
            )

        # 3. State Engine — current character states
        state = get_state(project_id)
        state_text = state.get("content", "").strip()[:1500] if state else ""

        # 4. Get model
        from engine.db import get_setting
        model_value = get_setting("model") or ""
        if not model_value:
            return jsonify({"error": "Не задана модель в настройках"}), 400

        api_key = get_api_key(project_id)

        # 5. Build LLM prompt
        sys_prompt = (
            "Ты — литературный ассистент. Помогаешь автору составить промт для генерации главы. "
            "Анализируешь контекст серии и создаёшь структурированный черновик промта. "
            "Пишешь лаконично и конкретно — автор сам доработает детали."
        )

        context_parts = []
        if plot_text:
            # Extract relevant chapter plan
            lines = plot_text.split('\n')
            relevant = []
            capture = False
            for line in lines:
                if f"{chapter_num}" in line or f"Гл.{chapter_num}" in line or f"Глава {chapter_num}" in line:
                    capture = True
                if capture:
                    relevant.append(line)
                    if len(relevant) > 15:
                        break
            if relevant:
                context_parts.append(f"ПЛАН СЕРИИ (фрагмент про гл.{chapter_num}):\n" + "\n".join(relevant))
            else:
                context_parts.append(f"ПЛАН СЕРИИ:\n{plot_text[:1000]}")

        if prev_l3_text:
            context_parts.append(f"САММАРИ ПРЕДЫДУЩЕЙ ГЛАВЫ:\n{prev_l3_text}")

        if state_text:
            context_parts.append(f"ТЕКУЩЕЕ СОСТОЯНИЕ ПЕРСОНАЖЕЙ:\n{state_text[:800]}")

        user_prompt = (
            "\n\n---\n\n".join(context_parts) +
            f"\n\n---\n\nСоставь черновик промта для Главы {chapter_num}.\n\n"
            "Формат строго такой:\n"
            f"Гл.{chapter_num} — [НАЗВАНИЕ ЗАГЛАВНЫМИ]\n\n"
            "ЗАДАЧА: [одно предложение — что должна сделать эта глава с читателем]\n\n"
            "СЦЕНЫ:\n"
            "1. [Локация — краткое описание]\n"
            "2. [Локация — краткое описание]\n"
            "3. [Локация — краткое описание]\n\n"
            "ТОНАЛЬНОСТЬ: [2-3 слова]\n"
            "ЗАКАНЧИВАЕТСЯ НА: [крючок или состояние]\n\n"
            "Не добавляй объяснений — только сам промт."
        )

        # 6. Call LLM
        from engine.pipeline import call_llm
        result = call_llm(model_value, sys_prompt, user_prompt, max_tokens=600)

        if not result or len(result.strip()) < 50:
            return jsonify({"error": "Модель вернула пустой ответ"}), 500

        return jsonify({"ok": True, "prompt": result.strip()})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
    except Exception:
        pass

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
