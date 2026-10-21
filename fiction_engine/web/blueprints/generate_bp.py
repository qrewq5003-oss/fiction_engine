"""Blueprint: генерация, pipeline, prep, prompt, edit, validate."""
from flask import Blueprint, request, jsonify, redirect, url_for
from engine.db import get_api_key, get_generation_history, get_generation_by_id
from engine.pipeline import score_text  # публичный API скоринга
from ..ownership import owned_generation, deny
from .helpers import get_current_project

bp = Blueprint("generate", __name__)



# /generate/run, /generate/status, /generate/save удалены 21.10: страницу
# «Генерация» слили с «Мастерской», и их не вызывал никто; /generate/save к тому
# же откатывал State поверх главы, не вливая анализ нового текста

@bp.route("/generate")
def generate_page():
    """Страница слита с Pipeline в «Мастерскую» (переключатель «Критик и судья»).
    Адрес оставлен: закладки и старые ссылки ведут туда."""
    return redirect(url_for("generate.pipeline_page"))


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
        return jsonify({"ok": False, "blocking": [], "warnings": [], "error": str(e)})


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
    from engine.db import get_generation_by_id, save_generation_score
    rec = get_generation_by_id(gen_id)
    if not rec:
        return jsonify({"error": "Запись не найдена"}), 404
    text = rec.get("result_text", "")
    if not text or len(text.strip()) < 50:
        return jsonify({"error": "Текст слишком короткий"}), 400
    # Оценщик — другой семьи, чем писатель этого текста (pipeline_config.scorer_model_for):
    # раньше без настройки оценивал сам писатель
    from engine.pipeline_config import scorer_model_for
    scorer_model = scorer_model_for(rec.get("model", ""))
    if not scorer_model:
        return jsonify({"error": "Нет оценщика другого семейства, чем писатель: выбери его в "
                                 "«Настройки → Оценщик» или набор ролей"}), 400
    current = get_current_project()
    from engine.unified_engine import project_genre_key
    genre = project_genre_key(current) or ""
    provider = scorer_model.split("::")[0] if "::" in scorer_model else ""
    if not get_api_key(provider):
        return jsonify({"error": f"Нет API ключа для {provider}"}), 400
    try:
        from engine.genre_mix import review_layers_note
        details = score_text(text, genre, scorer_model,
                             review_layers_note(current, rec.get("chapter_num")))
        save_generation_score(current["id"], gen_id, details["total"], details)
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
