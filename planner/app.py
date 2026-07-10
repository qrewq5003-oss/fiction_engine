"""
app.py — планировщик истории.
Запуск: python app.py
Порт: 5001
"""
from flask import Flask, redirect, url_for, session, request, jsonify, render_template
import os

app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
app.secret_key = os.environ.get("SECRET_KEY", "planner-secret-2026")

# ─── Init DB ─────────────────────────────────────────────────────────────────
from engine.db import init_db
init_db()

# ─── Blueprints ───────────────────────────────────────────────────────────────
from web.blueprints.main_bp   import bp as main_bp
from web.blueprints.scene_bp  import bp as scene_bp
from web.blueprints.api_bp    import bp as api_bp

app.register_blueprint(main_bp)
app.register_blueprint(scene_bp)
app.register_blueprint(api_bp)

# ─── Context processor ───────────────────────────────────────────────────────
@app.context_processor
def inject_globals():
    from engine.db import get_projects, get_project
    projects = get_projects()
    current_id = session.get("project_id")
    current = get_project(current_id) if current_id else None
    if not current and projects:
        current = projects[0]
        session["project_id"] = current["id"]
    return {"projects": projects, "current": current}


@app.route("/")
def index():
    return redirect(url_for("main.board"))


@app.route("/switch/<int:pid>")
def switch_project(pid):
    session["project_id"] = pid
    return redirect(url_for("main.board"))


if __name__ == "__main__":
    print("Планировщик запускается на http://localhost:5001")
    app.run(debug=False, host="0.0.0.0", port=5001)
