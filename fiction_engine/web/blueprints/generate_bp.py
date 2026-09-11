"""Blueprint: генерация, pipeline, prep, prompt, edit, validate."""
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from engine.db import (get_chapters, save_chapter, get_api_key,
                       get_generation_history, get_generation_by_id)
from engine.api import get_all_models_flat
from engine.pipeline import score_text  # публичный API скоринга
from ..ownership import owned_generation, deny
from .helpers import get_current_project, after_chapter_saved, log_web_error

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


@bp.route("/generate")
def generate_page():
    current = get_current_project()
    if not current:
        flash("Сначала выбери проект", "error")
        return redirect(url_for("index"))
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


@bp.route("/api/generation/history")
def generation_history():
    current = get_current_project()
    if not current:
        return jsonify([])
    return jsonify(get_generation_history(current["id"]))


@bp.route("/api/generation/<int:gen_id>")
def generation_detail(gen_id):
    # Номер генерации сквозной по всей базе: без проверки отдавался
    # текст главы из другого проекта.
    gen = owned_generation(gen_id)
    if not gen:
        return deny("Генерация")
    return jsonify(gen)


@bp.route("/api/generation/<int:gen_id>/score", methods=["POST"])
def generation_score(gen_id):
    if not owned_generation(gen_id):
        return deny("Генерация")
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
    except Exception as e:
        log_web_error("не прочитать scorer_model из настроек", e)
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

# ─── Маршруты, вынесенные в отдельные модули ──────────────────────────────────
#
# Импорт в самом низу — стандартный приём Flask: подмодули берут bp
# отсюда, поэтому импортировать их раньше создания bp нельзя.
# Блупринт один на все четыре файла, имена endpoint'ов не меняются.
from . import generate_prompt      # noqa: E402,F401
from . import generate_pipeline    # noqa: E402,F401
from . import generate_narrative   # noqa: E402,F401
