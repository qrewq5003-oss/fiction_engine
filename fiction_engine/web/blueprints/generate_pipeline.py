#!/usr/bin/env python3
"""
Полный цикл: генератор → критик → редактор → судья.

Выделено из generate_bp.py. Блупринт общий — см. generate_prompt.
"""

from flask import render_template, request, jsonify, redirect, url_for, flash
from engine.db import (get_chapters, save_chapter, get_api_key,
                       save_author_edit, get_pipeline_iterations)
from engine.api import get_all_models_flat


from .generate_bp import bp
from ..ownership import owned_run, deny
from .helpers import (get_current_project, log_web_error)


@bp.route("/pipeline")
def pipeline_page():
    current = get_current_project()
    if not current:
        flash("Сначала выбери проект", "error")
        return redirect(url_for("index"))
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
    if data.get("run_id") and not owned_run(data["run_id"]):
        return deny("Запуск")
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
                mark_update_applied(project_id, auto_id)
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
    if data.get("run_id") and not owned_run(data["run_id"]):
        return deny("Запуск")
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
        except Exception as e:
            # Некритично — не ломаем accept, но и не молчим:
            # без этой записи DATA_DRIVEN_LEARNING останется без данных
            log_web_error("accept: не записана правка автора", e,
                          project_id=current["id"], chapter_num=chapter_num)

    return jsonify({"ok": True, "state_updated": state_updated})


@bp.route("/pipeline/reject", methods=["POST"])
def pipeline_reject():
    run_id = (request.json or {}).get("run_id")
    if not run_id:
        return jsonify({"error": "Нет run_id"}), 400
    # Номер запуска сквозной: без проверки отклонялся чужой запуск.
    if not owned_run(run_id):
        return deny("Запуск")
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
        except Exception as e:
            log_web_error("reject: не записано отклонение", e,
                          project_id=current["id"])

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
    if not owned_run(run_id):
        return deny("Запуск")
    from engine.db import get_pipeline_run, get_pipeline_iterations
    run = get_pipeline_run(run_id)
    if not run:
        return jsonify({"error": "Не найден"}), 404
    iters = get_pipeline_iterations(run_id)
    return jsonify({"run": dict(run), "iterations": iters})


@bp.route("/pipeline/<int:run_id>/compare")
def pipeline_compare(run_id):
    if not owned_run(run_id):
        return deny("Запуск")
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
