"""Blueprint: база знаний проекта."""
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from engine.db import kb_get_all, kb_get, kb_save, kb_delete, kb_search
from .helpers import get_current_project

bp = Blueprint("knowledge", __name__)


@bp.route("/knowledge")
def knowledge_page():
    current = get_current_project()
    if not current:
        flash("Сначала выбери проект", "error")
        return redirect(url_for("index"))
    articles = kb_get_all(current["id"])
    return render_template("knowledge.html", current=current, articles=articles)


@bp.route("/api/knowledge", methods=["GET"])
def knowledge_list():
    current = get_current_project()
    if not current:
        return jsonify({"articles": []})
    return jsonify({"articles": kb_get_all(current["id"])})


@bp.route("/api/knowledge/save", methods=["POST"])
def knowledge_save():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    data = request.json or {}
    title   = data.get("title", "").strip()
    content = data.get("content", "").strip()
    tags    = data.get("tags", "").strip()
    auto_inject = int(data.get("auto_inject", 0))
    article_id  = data.get("id")

    if not title or not content:
        return jsonify({"error": "Нужны title и content"}), 400

    saved_id = kb_save(current["id"], title, content, tags, auto_inject, article_id)
    return jsonify({"ok": True, "id": saved_id})


@bp.route("/api/knowledge/<int:article_id>", methods=["GET"])
def knowledge_get(article_id):
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    art = kb_get(article_id)
    if not art or art["project_id"] != current["id"]:
        return jsonify({"error": "Не найдено"}), 404
    return jsonify(art)


@bp.route("/api/knowledge/<int:article_id>/delete", methods=["POST"])
def knowledge_delete(article_id):
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    kb_delete(article_id, current["id"])
    return jsonify({"ok": True})


@bp.route("/api/knowledge/search")
def knowledge_search():
    current = get_current_project()
    if not current:
        return jsonify({"articles": []})
    query = request.args.get("q", "")
    results = kb_search(current["id"], query, max_results=5)
    return jsonify({"articles": results})
