"""Blueprint: State Engine."""
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from engine.db import (get_state, update_state, get_api_key, get_pending_updates,
 mark_update_applied)
from engine.state import analyze_chapter
from engine.api import get_all_models_flat
from .helpers import get_current_project, log_web_error, read_uploaded_text
from ..ownership import deny

bp = Blueprint("state", __name__)


@bp.route("/state")
def state_view():
    current = get_current_project()
    if not current:
        flash("Сначала выбери проект", "error")
        return redirect(url_for("index"))
    state = get_state(current["id"])
    pending = get_pending_updates(current["id"])
    models = get_all_models_flat()
    return render_template("state.html", state=state, current=current, state_version=state_version(state),
                           pending=pending, models=models)


def state_version(state: dict) -> str:
    """Отпечаток State: форма несёт его с открытия страницы (state_edit)."""
    import hashlib
    return hashlib.sha1("|".join(state.get(k) or "" for k in ("global_state", "plot_matrix", "memory_graph"))
                        .encode("utf-8")).hexdigest()


@bp.route("/state/edit", methods=["POST"])
def state_edit():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    # State изменился, пока страница была открыта (приняли или пересчитали
    # главу) — не перетирать молча: форма сохраняет State целиком, и вписанное
    # главами пропадало (разбор 21.10). Страница — с правками автора и
    # предупреждением; повторное «Сохранить» (с новым отпечатком) пишет их
    now = get_state(current["id"])
    sent = request.form.get("state_version")
    if sent and sent != state_version(now):
        mine = {k: request.form.get(k) or "" for k in ("global_state", "plot_matrix", "memory_graph")}
        return render_template("state.html", state=mine, current=current, state_version=state_version(now),
                               state_conflict=True, pending=get_pending_updates(current["id"]),
                               models=get_all_models_flat()), 409
    update_state(current["id"],
                 global_state=request.form.get("global_state"),
                 plot_matrix=request.form.get("plot_matrix"),
                 memory_graph=request.form.get("memory_graph"),
                 _snapshot_reason="ручное редактирование")
    flash("State Engine обновлён", "success")
    return redirect(url_for("state.state_view"))


@bp.route("/state/import", methods=["POST"])
def state_import():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    from .helpers import NO_MODEL, page_model
    model_value = page_model((request.form or request.json or {}).get("model", ""))
    if not model_value:
        return jsonify({"error": NO_MODEL}), 400
    raw_text = ""
    if "file" in request.files:
        try:
            raw_text = read_uploaded_text(request.files["file"])
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
    else:
        raw_text = (request.form or {}).get("text", "").strip()
    if not raw_text:
        return jsonify({"error": "Нет текста"}), 400
    raw_text = raw_text[:40000]
    prompt = f"""Структурируй материал для State Engine. Отвечай только JSON.
ТЕКСТ:
{raw_text}
{{"global_state":"## ПЕРСОНАЖИ\\n...","plot_matrix":"## ОСНОВНАЯ ЛИНИЯ\\n...","memory_graph":"## КЛЮЧЕВЫЕ СОБЫТИЯ\\n..."}}"""
    try:
        from engine.pipeline import call_json
        parsed = call_json(model_value, "Ты помощник писателя. Только JSON.",
                           prompt, max_tokens=2000)
        return jsonify({"ok": True,
                        "global_state": parsed.get("global_state", ""),
                        "plot_matrix":  parsed.get("plot_matrix", ""),
                        "memory_graph": parsed.get("memory_graph", "")})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Фоновый анализ (polling) ────────────────────────────────────────────────
import threading, uuid as _uuid

_analyze_jobs: dict[str, dict] = {}
_analyze_lock = threading.Lock()
_ANALYZE_JOBS_KEEP = 50


def _cleanup_analyze_jobs():
    """
    Держим не больше 50 последних задач.

    Раньше словарь рос без ограничений, а каждая запись хранит полный текст
    анализа главы и next_context — на долгоживущем сервере это утечка.
    """
    with _analyze_lock:
        if len(_analyze_jobs) > _ANALYZE_JOBS_KEEP:
            for k in list(_analyze_jobs.keys())[:-_ANALYZE_JOBS_KEEP]:
                del _analyze_jobs[k]


@bp.route("/state/analyze", methods=["POST"])
def state_analyze():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    data = request.get_json(silent=True) or {}
    chapter_num = data.get("chapter_num")
    model_value = data.get("model")
    if not chapter_num or not model_value:
        return jsonify({"error": "Нужны chapter_num и model"}), 400
    provider = model_value.split("::")[0]
    if not get_api_key(provider):
        return jsonify({"error": f"Нет ключа для {provider}"}), 400

    _cleanup_analyze_jobs()
    job_id = str(_uuid.uuid4())
    with _analyze_lock:
        _analyze_jobs[job_id] = {"status": "running", "result": None, "error": None,
                                 "project_id": current["id"]}

    project_id = current["id"]

    def _worker():
        try:
            result = analyze_chapter(project_id, chapter_num, model_value)
            response = {"ok": True, "update_id": result["update_id"],
                        "analysis": result["analysis"],
                        "next_context": result["next_context"],
                        "chapter_num": chapter_num}
            try:
                from engine.pipeline import auto_drift_check_if_needed
                from engine.db import get_chapter as _get_ch
                ch = _get_ch(project_id, chapter_num)
                if ch:
                    drift = auto_drift_check_if_needed(project_id, chapter_num, ch["content"], model_value)
                    if drift and drift.get("warning"):
                        response["drift_warning"] = drift["warning"]
                        response["drift_score"] = drift.get("score")
            except Exception as e:
                log_web_error("анализ главы: проверка дрейфа голоса", e,
                              project_id=project_id, chapter_num=chapter_num)
            with _analyze_lock:
                _analyze_jobs[job_id]["status"] = "done"
                _analyze_jobs[job_id]["result"] = response
        except Exception as e:
            with _analyze_lock:
                _analyze_jobs[job_id]["status"] = "error"
                _analyze_jobs[job_id]["error"] = str(e)

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"ok": True, "job_id": job_id})


@bp.route("/state/analyze/status/<job_id>")
def state_analyze_status(job_id):
    current = get_current_project()
    with _analyze_lock:
        job = _analyze_jobs.get(job_id)
    # Анализ другого проекта — как несуществующий: после переключения проекта
    # страница State показывала чужой разбор (разбор 21.10)
    if not job or not current or job.get("project_id") != current["id"]:
        return jsonify({"status": "not_found"}), 404
    return jsonify({"status": job["status"], "result": job["result"], "error": job["error"]})


@bp.route("/state/apply/<int:update_id>", methods=["POST"])
def state_apply(update_id):
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    data = request.json or {}
    new_global = data.get("global_state")
    new_plot   = data.get("plot_matrix")
    new_memory = data.get("memory_graph")
    if new_global or new_plot or new_memory:
        update_state(current["id"], new_global, new_plot, new_memory,
                     _snapshot_reason="применение анализа")
        return jsonify({"ok": True, "message": "State Engine обновлён", "merge": None})
    try:
        from engine.db import get_pending_updates, merge_analysis_into_state
        updates = get_pending_updates(current["id"])
        for u in updates:
            if u["id"] == update_id and u.get("raw_analysis"):
                result = merge_analysis_into_state(
                    current["id"], u["raw_analysis"], u.get("chapter_num", 0)
                )
                if result.get("error"):
                    # Не помечаем применённым: анализ остаётся в очереди, его можно переделать
                    return jsonify({"error": result["error"] + ". Запусти анализ главы ещё раз."}), 422
                mark_update_applied(current["id"], update_id)
                if result["changed"]:
                    return jsonify({"ok": True,
                                    "message": f"Применено {len(result['fields'])} изменений",
                                    "merge": result})
                else:
                    return jsonify({"ok": True,
                                    "message": "Изменений не обнаружено",
                                    "merge": {"changed": False, "fields": [], "new_chars": []}})
    except Exception as e:
        # Слияние сорвалось — анализ остаётся в очереди, а не «применён» молча
        # (раньше помечался применённым и пропадал; разбор 21.10)
        log_web_error("state/apply: слияние анализа сорвалось", e,
                      project_id=current["id"])
        return jsonify({"error": f"Слияние анализа сорвалось: {str(e)[:200]}. Анализ остался в очереди."}), 500
    if not mark_update_applied(current["id"], update_id):
        return deny("Обновление состояния")
    return jsonify({"ok": True, "message": "State Engine обновлён", "merge": None})


@bp.route("/state/discard/<int:update_id>", methods=["POST"])
def state_discard(update_id):
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    if not mark_update_applied(current["id"], update_id):
        return deny("Обновление состояния")
    return jsonify({"ok": True})


# ─── API: история и откат ────────────────────────────────────────────────────

@bp.route("/api/state/history")
def state_history():
    current = get_current_project()
    if not current:
        return jsonify({"history": []})
    from engine.db import get_state_history
    return jsonify({"history": get_state_history(current["id"])})


@bp.route("/api/state/restore/<int:snapshot_id>", methods=["POST"])
def state_restore(snapshot_id):
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    from engine.db import restore_state_snapshot
    ok = restore_state_snapshot(current["id"], snapshot_id)
    return jsonify({"ok": True}) if ok else jsonify({"error": "Снапшот не найден"}), 404
