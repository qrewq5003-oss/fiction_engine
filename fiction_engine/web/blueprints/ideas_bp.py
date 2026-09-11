"""Blueprint: Ideas workspace + эталоны + оценка с подсветкой."""
from flask import Blueprint, render_template, request, jsonify
from engine.db import (create_project, set_active_project, update_state)
from engine.api import get_all_models_flat
from .helpers import get_current_project

bp = Blueprint("ideas", __name__)


@bp.route("/ideas")
def ideas_view():
    from engine.db import get_projects
    current = get_current_project()
    projects = get_projects()
    models = get_all_models_flat()
    return render_template("ideas.html", current=current, projects=projects, models=models)


@bp.route("/ideas/accept", methods=["POST"])
def ideas_accept():
    data = request.json or {}
    text      = (data.get("text") or "").strip()
    action    = data.get("action", "state")
    model_v   = data.get("model", "")
    proj_name = (data.get("project_name") or "").strip()
    genre     = (data.get("genre") or "").strip()
    if not text:
        return jsonify({"error": "Нет текста"}), 400
    if not model_v:
        return jsonify({"error": "Не задана модель"}), 400

    prompt = f"""Структурируй идеи для художественного проекта. Только JSON.
ТЕКСТ:\n{text[:35000]}
{{"project_name":"...","genre":"...","global_state":"## ПЕРСОНАЖИ\\n...","plot_matrix":"## ОСНОВНАЯ ЛИНИЯ\\n...","memory_graph":"## КЛЮЧЕВЫЕ СОБЫТИЯ\\n..."}}"""

    try:
        from engine.pipeline import call_json
        parsed = call_json(model_v, "Ты помощник писателя. Только JSON.",
                           prompt, max_tokens=2500)
        gs = parsed.get("global_state", "")
        pm = parsed.get("plot_matrix", "")
        mg = parsed.get("memory_graph", "")

        if action == "project":
            name = proj_name or parsed.get("project_name") or "Новый проект"
            g    = genre or parsed.get("genre") or ""
            pid  = create_project(name, g)
            set_active_project(pid)
            update_state(pid, gs, pm, mg)
            return jsonify({"ok": True, "action": "project", "project_id": pid,
                            "project_name": name, "global_state": gs,
                            "plot_matrix": pm, "memory_graph": mg})
        else:
            current = get_current_project()
            if not current:
                return jsonify({"error": "Нет активного проекта"}), 400
            update_state(current["id"], gs, pm, mg)
            return jsonify({"ok": True, "action": "state",
                            "global_state": gs, "plot_matrix": pm, "memory_graph": mg})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Эталоны ─────────────────────────────────────────────────────────────────

@bp.route("/api/exemplars")
def exemplars_list():
    current = get_current_project()
    if not current:
        return jsonify({"exemplars": []})
    from engine.db import get_exemplars
    return jsonify({"exemplars": get_exemplars(current["id"])})


@bp.route("/api/exemplars/save", methods=["POST"])
def exemplar_save():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    data = request.json or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Нет текста"}), 400
    from engine.db import save_exemplar
    eid = save_exemplar(current["id"], data.get("chapter_num", 0),
                        text, (data.get("label") or "").strip())
    return jsonify({"ok": True, "id": eid})


@bp.route("/api/exemplars/<int:eid>/delete", methods=["POST"])
def exemplar_delete(eid):
    from engine.db import delete_exemplar
    delete_exemplar(eid)
    return jsonify({"ok": True})


# ─── Оценка с подсветкой ─────────────────────────────────────────────────────

@bp.route("/score")
def score_view():
    models = get_all_models_flat()
    return render_template("score.html", models=models)


@bp.route("/api/score/annotate", methods=["POST"])
def score_annotate():
    current = get_current_project()
    data = request.json or {}
    text = (data.get("text") or "").strip()
    model_value = (data.get("model") or "").strip()
    if not text or not model_value:
        return jsonify({"error": "Нужны text и model"}), 400

    exemplar_text = ""
    if current:
        from engine.db import get_exemplars
        exemplars = get_exemplars(current["id"])
        if exemplars:
            exemplar_text = exemplars[0]["text"][:600]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()][:20]
    if not paragraphs:
        return jsonify({"error": "Нет абзацев"}), 400

    exemplar_block = f"\nЭТАЛОН (сравни голос):\n{exemplar_text}\n" if exemplar_text else ""
    prompt = f"""Ты литературный редактор. Оцени каждый абзац.
{exemplar_block}
ТЕКСТ:\n""" + "\n\n".join(f"[{i+1}] {p}" for i, p in enumerate(paragraphs)) + """

Для каждого абзаца: score 1-10, color (green/yellow/red), comment (1 предложение).
{"paragraphs":[{"index":1,"score":8,"color":"green","comment":"..."}]}"""

    try:
        from engine.pipeline import call_json, _call
        import json, re
        # Пробуем через call_json
        try:
            result = call_json(model_value, "Ты литературный редактор. Только JSON.",
                               prompt, max_tokens=1500)
        except Exception:
            # Fallback: вызываем напрямую и чистим markdown-фенсы
            raw = _call(model_value, "Ты литературный редактор. Только JSON.",
                        prompt, max_tokens=1500)
            raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
            raw = re.sub(r"\s*```$", "", raw.strip())
            result = json.loads(raw)
        for item in result.get("paragraphs", []):
            idx = item.get("index", 1) - 1
            if 0 <= idx < len(paragraphs):
                item["text"] = paragraphs[idx]
        return jsonify({"ok": True, "paragraphs": result.get("paragraphs", [])})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/score/calibrate", methods=["POST"])
def score_calibrate():
    """
    Сохранить авторскую оценку главы для калибровки судьи.

    Тело запроса: {chapter_num, judge_score, author_score, note?}

    После 3+ коррекций судья начинает получать подсказку:
    «Ты обычно завышаешь на +3.2 пункта — скорректируй ИТОГ».
    """
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет активного проекта"}), 400

    data = request.json or {}
    chapter_num  = data.get("chapter_num")
    judge_score  = data.get("judge_score")
    author_score = data.get("author_score")
    note         = (data.get("note") or "").strip()

    if chapter_num is None or judge_score is None or author_score is None:
        return jsonify({"error": "Нужны chapter_num, judge_score, author_score"}), 400

    try:
        chapter_num  = int(chapter_num)
        judge_score  = float(judge_score)
        author_score = float(author_score)
    except (TypeError, ValueError):
        return jsonify({"error": "Неверный тип данных"}), 400

    if not (0 <= judge_score <= 50) or not (0 <= author_score <= 50):
        return jsonify({"error": "Оценки должны быть в диапазоне 0–50"}), 400

    from engine.db import save_judge_calibration, get_judge_calibration_hint
    ok = save_judge_calibration(
        current["id"], chapter_num, judge_score, author_score, note
    )
    if not ok:
        return jsonify({"error": "Ошибка сохранения"}), 500

    hint = get_judge_calibration_hint(current["id"])
    delta = author_score - judge_score
    return jsonify({
        "ok": True,
        "delta": round(delta, 1),
        "calibration_hint": hint,
        "message": (
            f"Сохранено: судья {judge_score}/50, ваша оценка {author_score}/50 "
            f"(δ {delta:+.1f}). {hint}"
        ),
    })
